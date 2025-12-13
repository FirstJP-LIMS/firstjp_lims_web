from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required

from ..models import Cohort, CohortMembership


def cohort_detail_view(request, cohort_id):
    cohort = get_object_or_404(Cohort.objects.select_related("course", "facilitator"), id=cohort_id)
    members = cohort.memberships.select_related("learner").all()
    return render(request, "learn/cohorts/cohort_detail.html", {"cohort": cohort, "members": members})


@login_required
def cohort_join_view(request, cohort_id):
    cohort = get_object_or_404(Cohort, id=cohort_id)
    # optionally enforce capacity
    if cohort.capacity and cohort.memberships.count() >= cohort.capacity:
        messages.error(request, "Cohort is full.")
        return redirect("learn:cohort_detail", cohort_id=cohort.id)

    membership, created = CohortMembership.objects.get_or_create(cohort=cohort, learner=request.user)
    if created:
        messages.success(request, f"You joined cohort {cohort.title}.")
    else:
        messages.info(request, "You are already a member of this cohort.")
    return redirect("learn:cohort_detail", cohort_id=cohort.id)
