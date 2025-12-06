import pytest
from decimal import Decimal
from django.utils import timezone
from apps.master.models import PriceList, CorporatePlan
from apps.laboratory.models import TestAssignment, TestRequest
from apps.billing.models import BillingInformation, Payment, Invoice
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestBillingModel:

    def setup_method(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="pass123"
        )

        self.price_list = PriceList.objects.create(
            name="Standard",
            is_default=True,
            default_discount_percentage=Decimal("10.00"),
            default_discount_cap=Decimal("500.00")
        )

        self.request = TestRequest.objects.create(
            request_number="REQ001",
            created_by=self.user,
        )

        self.assignment = TestAssignment.objects.create(
            test_request=self.request,
            test_name="Full Blood Count",
            quantity=1
        )

    def test_billing_calculation(self):
        """Test discount + price + tax logic"""
        billing = BillingInformation.objects.create(
            test_request=self.request,
            assignment=self.assignment,
            price_list=self.price_list,
            original_price=Decimal("5000.00"),
            manual_discount=Decimal("200.00"),
            waiver_amount=Decimal("100.00"),
            discount_type="PERCENT",
            discount_percentage=Decimal("5.00"),
        )

        billing.recalculate()

        assert billing.discount >= 0
        assert billing.tax_amount >= 0
        assert billing.final_billable_amount > 0
        assert billing.total_payable > 0

    def test_waiver_reduces_final_amount(self):
        billing = BillingInformation.objects.create(
            test_request=self.request,
            assignment=self.assignment,
            price_list=self.price_list,
            original_price=Decimal("3000.00"),
            waiver_amount=Decimal("1000.00"),
        )
        billing.recalculate()

        assert billing.final_billable_amount == Decimal("2000.00")


@pytest.mark.django_db
class TestPaymentModel:

    def test_partial_payment(self):
        billing = BillingInformation.objects.create(
            original_price=Decimal("5000.00"),
            final_billable_amount=Decimal("5000.00"),
            total_payable=Decimal("5000.00"),
        )

        Payment.objects.create(
            billing=billing,
            amount=Decimal("2000.00"),
            payment_method="CASH"
        )

        assert billing.amount_paid == Decimal("2000.00")
        assert billing.outstanding_balance == Decimal("3000.00")
        assert billing.payment_status == "PARTIAL"

    def test_full_payment(self):
        billing = BillingInformation.objects.create(
            original_price=Decimal("5000.00"),
            final_billable_amount=Decimal("5000.00"),
            total_payable=Decimal("5000.00"),
        )

        Payment.objects.create(
            billing=billing,
            amount=Decimal("5000.00"),
            payment_method="CASH"
        )

        assert billing.payment_status == "PAID"
        assert billing.outstanding_balance == Decimal("0.00")


@pytest.mark.django_db
class TestInvoiceModel:

    def test_invoice_totals(self):
        invoice = Invoice.objects.create(
            invoice_number="INV001",
            client_name="ABC Corp",
            invoice_date=timezone.now()
        )

        b1 = BillingInformation.objects.create(
            invoice=invoice,
            final_billable_amount=Decimal("3000.00"),
            tax_amount=Decimal("150.00")
        )
        b2 = BillingInformation.objects.create(
            invoice=invoice,
            final_billable_amount=Decimal("2000.00"),
            tax_amount=Decimal("100.00")
        )

        invoice.calculate_totals()

        assert invoice.total_amount == Decimal("5000.00")
        assert invoice.total_tax == Decimal("250.00")
        assert invoice.grand_total == Decimal("5250.00")
