from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from core.utils import notify_staff

from .forms import EnquiryForm


def create_enquiry(request):
    if request.method != "POST":
        return redirect("core:contact")

    form = EnquiryForm(request.POST)
    if form.is_valid():
        enquiry = form.save()
        try:
            notify_staff(
                title=f"New website enquiry {enquiry.reference}",
                message=(
                    f"{enquiry.name}"
                    f"{' — ' + enquiry.company if enquiry.company else ''}: "
                    f"{enquiry.message[:180]}"
                ),
                url=reverse("dashboard:enquiry_detail", args=[enquiry.pk]),
                level="info",
            )
        except Exception:
            # A notification failure must never lose a customer enquiry.
            pass
        messages.success(
            request,
            "Your enquiry has been recorded. Keep the reference number for follow-up.",
        )
        return redirect(
            f"{reverse('core:contact_success')}?{urlencode({'ref': enquiry.reference})}"
        )

    # Re-render the contact page with server-side validation errors and the
    # same managed-page content shown by the GET view.
    from cms.models import Page

    cms_page = Page.objects.filter(
        slug="contact", status=Page.STATUS_PUBLISHED
    ).first()
    return render(
        request,
        "pages/contact.html",
        {
            "form": form,
            "form_has_errors": True,
            "active_nav": "contact",
            "cms_page": cms_page,
        },
    )
