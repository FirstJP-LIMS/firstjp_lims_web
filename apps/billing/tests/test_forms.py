# import datetime
# from decimal import Decimal
# from django.test import TestCase
# from django.utils import timezone

# from billing.forms import (
#     InvoiceForm,
#     InvoiceUpdateForm,
#     PaymentForm
# )

# from billing.models import (
#     Invoice,
#     Payment,
#     Client
# )


# class InvoiceFormTests(TestCase):

#     def setUp(self):
#         self.client_obj = Client.objects.create(
#             name="Test Client",
#             email="client@example.com"
#         )

#     def test_invoice_form_valid_data(self):
#         """
#         Ensure the invoice form is valid with correct input.
#         """
#         form = InvoiceForm(data={
#             "client": self.client_obj.id,
#             "amount": "2500.50",
#             "due_date": (timezone.now() + datetime.timedelta(days=10)).date(),
#             "description": "LIMS Test Invoice"
#         })
#         self.assertTrue(form.is_valid())

#     def test_invoice_form_missing_required_fields(self):
#         form = InvoiceForm(data={})
#         self.assertFalse(form.is_valid())
#         self.assertIn("client", form.errors)
#         self.assertIn("amount", form.errors)
#         self.assertIn("due_date", form.errors)

#     def test_invoice_form_invalid_amount(self):
#         form = InvoiceForm(data={
#             "client": self.client_obj.id,
#             "amount": "-200",
#             "due_date": timezone.now().date()
#         })
#         self.assertFalse(form.is_valid())
#         self.assertIn("amount", form.errors)

#     def test_invoice_form_due_date_cannot_be_past(self):
#         form = InvoiceForm(data={
#             "client": self.client_obj.id,
#             "amount": "300.00",
#             "due_date": (timezone.now() - datetime.timedelta(days=1)).date(),
#         })
#         self.assertFalse(form.is_valid())
#         self.assertIn("due_date", form.errors)


# class InvoiceUpdateFormTests(TestCase):

#     def setUp(self):
#         self.client_obj = Client.objects.create(
#             name="Test Client",
#             email="client@example.com"
#         )
#         self.invoice = Invoice.objects.create(
#             client=self.client_obj,
#             amount=Decimal("500.00"),
#             due_date=timezone.now().date(),
#             description="Initial Invoice"
#         )

#     def test_invoice_update_valid(self):
#         form = InvoiceUpdateForm(data={
#             "amount": "750.00",
#             "description": "Updated invoice details",
#             "due_date": (timezone.now() + datetime.timedelta(days=5)).date()
#         })
#         self.assertTrue(form.is_valid())

#     def test_invoice_update_invalid_amount(self):
#         form = InvoiceUpdateForm(data={
#             "amount": "-900",
#             "due_date": timezone.now().date()
#         })
#         self.assertFalse(form.is_valid())
#         self.assertIn("amount", form.errors)

#     def test_invoice_update_past_due_date(self):
#         form = InvoiceUpdateForm(data={
#             "amount": "900",
#             "due_date": timezone.now().date() - datetime.timedelta(days=3)
#         })
#         self.assertFalse(form.is_valid())
#         self.assertIn("due_date", form.errors)


# class PaymentFormTests(TestCase):

#     def setUp(self):
#         self.client_obj = Client.objects.create(
#             name="Test Client",
#             email="client@example.com"
#         )
#         self.invoice = Invoice.objects.create(
#             client=self.client_obj,
#             amount=Decimal("1000.00"),
#             due_date=timezone.now().date() + datetime.timedelta(days=3),
#             description="Test Invoice"
#         )

#     def test_payment_form_valid_data(self):
#         form = PaymentForm(data={
#             "invoice": self.invoice.id,
#             "amount_paid": "600.00",
#             "payment_date": timezone.now().date(),
#             "method": "BANK_TRANSFER"
#         })
#         self.assertTrue(form.is_valid())

#     def test_payment_form_amount_exceeds_invoice(self):
#         form = PaymentForm(data={
#             "invoice": self.invoice.id,
#             "amount_paid": "1500.00",
#             "payment_date": timezone.now().date(),
#             "method": "CASH"
#         })
#         self.assertFalse(form.is_valid())
#         self.assertIn("amount_paid", form.errors)

#     def test_payment_form_negative_amount(self):
#         form = PaymentForm(data={
#             "invoice": self.invoice.id,
#             "amount_paid": "-200",
#             "payment_date": timezone.now().date(),
#         })
#         self.assertFalse(form.is_valid())
#         self.assertIn("amount_paid", form.errors)

#     def test_payment_form_missing_required_fields(self):
#         form = PaymentForm(data={})
#         self.assertFalse(form.is_valid())
#         self.assertIn("invoice", form.errors)
#         self.assertIn("amount_paid", form.errors)
#         self.assertIn("payment_date", form.errors)

#     def test_payment_form_invalid_payment_date(self):
#         future_date = timezone.now().date() + datetime.timedelta(days=4)
#         form = PaymentForm(data={
#             "invoice": self.invoice.id,
#             "amount_paid": "100",
#             "payment_date": future_date,
#         })
#         self.assertFalse(form.is_valid())
#         self.assertIn("payment_date", form.errors)
