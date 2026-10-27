from __future__ import annotations

import csv

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core.forms import staff_required
from core.models import ActivityLog
from core.utils import log_activity, notify_staff

from .forms import CustomerForm, EnquiryNoteForm, EnquiryUpdateForm
from .models import Customer, Enquiry, EnquiryNote

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Prevent spreadsheet formula injection in exported CSV files."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _csv_response(filename):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    return response


def _filtered_enquiries(request):
    enquiries = Enquiry.objects.select_related(
        "product", "product__category", "assigned_to", "customer"
    )
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    priority = (request.GET.get("priority") or "").strip()
    assigned = (request.GET.get("assigned") or "").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    followup = (request.GET.get("followup") or "").strip()

    if query:
        enquiries = enquiries.filter(
            Q(reference__icontains=query)
            | Q(name__icontains=query)
            | Q(company__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
            | Q(product__name__icontains=query)
        )
    if status:
        enquiries = enquiries.filter(status=status)
    if priority:
        enquiries = enquiries.filter(priority=priority)
    if assigned == "unassigned":
        enquiries = enquiries.filter(assigned_to__isnull=True)
    elif assigned.isdigit():
        enquiries = enquiries.filter(assigned_to_id=int(assigned))
    if followup == "due":
        enquiries = enquiries.filter(
            follow_up_date__lte=timezone.localdate(), status__in=Enquiry.OPEN_STATUSES
        )
    elif followup == "upcoming":
        enquiries = enquiries.filter(
            follow_up_date__gt=timezone.localdate(), status__in=Enquiry.OPEN_STATUSES
        )

    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None
    if date_from:
        enquiries = enquiries.filter(created_at__date__gte=date_from)
    if date_to:
        enquiries = enquiries.filter(created_at__date__lte=date_to)

    filters = {
        "query": query,
        "status": status,
        "priority": priority,
        "assigned": assigned,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "followup": followup,
    }
    return enquiries, filters


def _staff_users():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(is_active=True, is_staff=True).order_by(
        "first_name", "username"
    )


# ---------------------------------------------------------------------------
# Enquiries
# ---------------------------------------------------------------------------
@staff_required
@permission_required("enquiries.view_enquiry", raise_exception=True)
def enquiry_list(request):
    enquiries, filters = _filtered_enquiries(request)

    paginator = Paginator(enquiries, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)

    status_counts = dict(
        Enquiry.objects.values_list("status").annotate(total=Count("id"))
    )
    status_summary = [
        {"value": value, "label": label, "count": status_counts.get(value, 0)}
        for value, label in Enquiry.STATUS_CHOICES
    ]

    return render(
        request,
        "dashboard/enquiries/list.html",
        {
            "page_obj": page_obj,
            "enquiries": page_obj.object_list,
            "total_count": paginator.count,
            "all_enquiry_count": sum(status_counts.values()),
            "status_choices": Enquiry.STATUS_CHOICES,
            "priority_choices": Enquiry.PRIORITY_CHOICES,
            "status_counts": status_counts,
            "status_summary": status_summary,
            "staff_users": _staff_users(),
            "querystring": params.urlencode(),
            "followups_due": Enquiry.objects.filter(
                follow_up_date__lte=timezone.localdate(),
                status__in=Enquiry.OPEN_STATUSES,
            ).count(),
            **filters,
        },
    )


@staff_required
@permission_required("enquiries.view_enquiry", raise_exception=True)
def enquiry_export(request):
    enquiries, filters = _filtered_enquiries(request)
    response = _csv_response(
        f"spc-enquiries-{timezone.localdate():%Y%m%d}.csv"
    )
    writer = csv.writer(response)
    writer.writerow(
        [
            "Reference",
            "Received",
            "Updated",
            "Customer",
            "Company",
            "Email",
            "Phone",
            "Product",
            "Status",
            "Priority",
            "Source",
            "Assigned to",
            "Follow-up date",
            "Customer record",
            "Message",
            "Internal notes",
        ]
    )
    for enquiry in enquiries:
        writer.writerow(
            [
                _csv_safe(enquiry.reference),
                enquiry.created_at.strftime("%Y-%m-%d %H:%M"),
                enquiry.updated_at.strftime("%Y-%m-%d %H:%M"),
                _csv_safe(enquiry.name),
                _csv_safe(enquiry.company),
                _csv_safe(enquiry.email),
                _csv_safe(enquiry.phone),
                _csv_safe(enquiry.product_label),
                _csv_safe(enquiry.get_status_display()),
                _csv_safe(enquiry.get_priority_display()),
                _csv_safe(enquiry.source),
                _csv_safe(
                    enquiry.assigned_to.get_full_name() or enquiry.assigned_to.username
                    if enquiry.assigned_to
                    else "Unassigned"
                ),
                enquiry.follow_up_date or "",
                _csv_safe(enquiry.customer.name if enquiry.customer else ""),
                _csv_safe(enquiry.message),
                _csv_safe(enquiry.internal_notes),
            ]
        )
    log_activity(
        request,
        ActivityLog.ACTION_EXPORT,
        f"Exported {enquiries.count()} enquiry record(s)",
    )
    return response


@staff_required
@permission_required("enquiries.view_enquiry", raise_exception=True)
def enquiry_detail(request, pk):
    enquiry = get_object_or_404(
        Enquiry.objects.select_related(
            "product", "product__category", "assigned_to", "customer"
        ),
        pk=pk,
    )
    can_change = request.user.has_perm("enquiries.change_enquiry")
    can_delete = request.user.has_perm("enquiries.delete_enquiry")
    can_convert = request.user.has_perm("enquiries.add_customer")

    form = EnquiryUpdateForm(
        request.POST if request.method == "POST" and can_change else None,
        instance=enquiry,
    )

    if request.method == "POST":
        if not can_change:
            messages.error(request, "You do not have permission to update enquiries.")
            return redirect("dashboard:enquiry_detail", pk=enquiry.pk)
        old_status = enquiry.status
        old_assigned_to_id = enquiry.assigned_to_id
        old_follow_up_date = enquiry.follow_up_date
        if form.is_valid():
            enquiry = form.save()
            log_activity(
                request,
                ActivityLog.ACTION_UPDATE,
                f"Enquiry {enquiry.reference} updated"
                + (
                    f" (status {old_status} → {enquiry.status})"
                    if old_status != enquiry.status
                    else ""
                ),
                target=enquiry,
            )
            try:
                from email_manager.notifications import (
                    notify_assignment,
                    notify_status_change,
                )

                if old_status != enquiry.status:
                    notify_status_change(
                        enquiry, old_status, enquiry.status, actor=request.user
                    )
                if old_assigned_to_id != enquiry.assigned_to_id:
                    notify_assignment(enquiry, actor=request.user)
            except Exception:
                # Email failures never block a saved enquiry update.
                pass
            messages.success(request, f"Enquiry {enquiry.reference} updated.")
            return redirect("dashboard:enquiry_detail", pk=enquiry.pk)
        messages.error(request, "Please correct the highlighted fields.")

    email_logs = (
        enquiry.email_logs.select_related("triggered_by")
        .order_by("-created_at")[:12]
        if request.user.has_perm("email_manager.view_emaillog")
        else []
    )

    return render(
        request,
        "dashboard/enquiries/detail.html",
        {
            "enquiry": enquiry,
            "form": form,
            "note_form": EnquiryNoteForm(),
            "notes": enquiry.notes.select_related("author"),
            "can_change": can_change,
            "can_delete": can_delete,
            "can_convert": can_convert,
            "email_logs": email_logs,
            "can_view_email_logs": request.user.has_perm(
                "email_manager.view_emaillog"
            ),
            "can_manage_smtp": request.user.is_superuser
            or request.user.has_perm("email_manager.manage_smtp"),
        },
    )


@staff_required
@permission_required("enquiries.change_enquiry", raise_exception=True)
@require_POST
def enquiry_note_add(request, pk):
    enquiry = get_object_or_404(Enquiry, pk=pk)
    form = EnquiryNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.enquiry = enquiry
        note.author = request.user
        note.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Note added to enquiry {enquiry.reference}",
            target=enquiry,
        )
        messages.success(request, "Private note added to the enquiry history.")
    else:
        messages.error(request, "The note could not be saved. Please try again.")
    return redirect("dashboard:enquiry_detail", pk=enquiry.pk)


@staff_required
@permission_required("enquiries.change_enquiry", raise_exception=True)
@permission_required("enquiries.add_customer", raise_exception=True)
def enquiry_convert(request, pk):
    enquiry = get_object_or_404(
        Enquiry.objects.select_related("customer"), pk=pk
    )
    existing = enquiry.customer

    if request.method == "POST":
        if existing:
            messages.info(
                request,
                f"This enquiry is already linked to customer “{existing.name}”.",
            )
            return redirect("dashboard:customer_detail", pk=existing.pk)
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.created_by = request.user
            customer.save()
            enquiry.customer = customer
            enquiry.status = Enquiry.STATUS_CONVERTED
            enquiry.save(update_fields=["customer", "status", "updated_at"])
            log_activity(
                request,
                ActivityLog.ACTION_CREATE,
                f"Customer “{customer.name}” created from enquiry {enquiry.reference}",
                target=customer,
            )
            notify_staff(
                "Enquiry converted",
                f"{enquiry.reference} was converted to customer {customer.name}.",
                url=reverse("dashboard:customer_detail", args=[customer.pk]),
                level="success",
            )
            messages.success(
                request,
                f"Customer “{customer.name}” created and enquiry {enquiry.reference} marked as converted.",
            )
            return redirect("dashboard:customer_detail", pk=customer.pk)
    else:
        form = CustomerForm(
            initial={
                "name": enquiry.company or enquiry.name,
                "contact_person": enquiry.name,
                "email": enquiry.email,
                "phone": enquiry.phone,
                "notes": f"Created from enquiry {enquiry.reference}.",
            }
        )

    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": f"Convert enquiry {enquiry.reference}",
            "eyebrow": "Enquiries & customers",
            "description": (
                "Create a customer record from this enquiry. The enquiry will be "
                "linked to the customer and marked as Converted."
            ),
            "submit_label": "Create customer & convert",
            "cancel_url": reverse("dashboard:enquiry_detail", args=[enquiry.pk]),
            "sections": form.section_fields(),
            "object": enquiry,
            "secondary_actions": [],
        },
    )


@staff_required
@permission_required("enquiries.delete_enquiry", raise_exception=True)
def enquiry_delete(request, pk):
    enquiry = get_object_or_404(Enquiry, pk=pk)
    if request.method == "POST":
        reference = enquiry.reference
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Enquiry deleted: {reference}",
            target_type="enquiries.enquiry",
            target_id=enquiry.pk,
        )
        enquiry.delete()
        messages.success(request, f"Enquiry {reference} deleted.")
        return redirect("dashboard:enquiry_list")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete enquiry",
            "object_label": f"{enquiry.reference} — {enquiry.name}",
            "object_type": "enquiry",
            "warning": "This permanently removes the customer enquiry and its internal notes. Customer records are not affected.",
            "cancel_url": reverse("dashboard:enquiry_detail", args=[enquiry.pk]),
        },
    )


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
@staff_required
@permission_required("enquiries.view_customer", raise_exception=True)
def customer_list(request):
    customers = Customer.objects.annotate(
        enquiry_total=Count("enquiries"),
        open_total=Count(
            "enquiries",
            filter=Q(enquiries__status__in=Enquiry.OPEN_STATUSES),
        ),
    )
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if query:
        customers = customers.filter(
            Q(name__icontains=query)
            | Q(contact_person__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    if status:
        customers = customers.filter(status=status)
    customers = customers.order_by("name")

    paginator = Paginator(customers, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    status_counts = dict(
        Customer.objects.values_list("status").annotate(total=Count("id"))
    )

    return render(
        request,
        "dashboard/customers/list.html",
        {
            "customers": page_obj.object_list,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "all_customer_count": Customer.objects.count(),
            "query": query,
            "status": status,
            "status_choices": Customer.STATUS_CHOICES,
            "status_counts": status_counts,
            "querystring": params.urlencode(),
        },
    )


@staff_required
@permission_required("enquiries.view_customer", raise_exception=True)
def customer_export(request):
    customers = Customer.objects.prefetch_related("enquiries")
    query = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if query:
        customers = customers.filter(
            Q(name__icontains=query)
            | Q(contact_person__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    if status:
        customers = customers.filter(status=status)

    response = _csv_response(f"spc-customers-{timezone.localdate():%Y%m%d}.csv")
    writer = csv.writer(response)
    writer.writerow(
        [
            "Customer",
            "Contact person",
            "Email",
            "Phone",
            "Status",
            "Enquiries",
            "Address",
            "Notes",
            "Created",
        ]
    )
    for customer in customers:
        writer.writerow(
            [
                _csv_safe(customer.name),
                _csv_safe(customer.contact_person),
                _csv_safe(customer.email),
                _csv_safe(customer.phone),
                _csv_safe(customer.get_status_display()),
                customer.enquiry_count,
                _csv_safe(customer.company_address),
                _csv_safe(customer.notes),
                customer.created_at.strftime("%Y-%m-%d"),
            ]
        )
    log_activity(
        request,
        ActivityLog.ACTION_EXPORT,
        f"Exported {customers.count()} customer record(s)",
    )
    return response


@staff_required
@permission_required("enquiries.add_customer", raise_exception=True)
def customer_create(request):
    form = CustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        customer = form.save(commit=False)
        customer.created_by = request.user
        customer.save()
        log_activity(
            request,
            ActivityLog.ACTION_CREATE,
            f"Customer created: {customer.name}",
            target=customer,
        )
        messages.success(request, f"Customer “{customer.name}” created.")
        return redirect("dashboard:customer_detail", pk=customer.pk)

    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": "Add customer",
            "eyebrow": "Enquiries & customers",
            "description": "Create a customer record manually, or convert a qualified enquiry.",
            "submit_label": "Create customer",
            "cancel_url": reverse("dashboard:customer_list"),
            "sections": form.section_fields(),
        },
    )


@staff_required
@permission_required("enquiries.view_customer", raise_exception=True)
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    enquiries = customer.enquiries.select_related("product", "assigned_to").order_by(
        "-created_at"
    )
    return render(
        request,
        "dashboard/customers/detail.html",
        {
            "customer": customer,
            "enquiries": enquiries,
            "enquiry_count": enquiries.count(),
            "open_count": enquiries.filter(
                status__in=Enquiry.OPEN_STATUSES
            ).count(),
            "converted_count": enquiries.filter(
                status=Enquiry.STATUS_CONVERTED
            ).count(),
            "can_change": request.user.has_perm("enquiries.change_customer"),
            "can_delete": request.user.has_perm("enquiries.delete_customer"),
            "can_add_enquiry": request.user.has_perm("enquiries.add_enquiry"),
        },
    )


@staff_required
@permission_required("enquiries.change_customer", raise_exception=True)
def customer_edit(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        log_activity(
            request,
            ActivityLog.ACTION_UPDATE,
            f"Customer updated: {customer.name}",
            target=customer,
        )
        messages.success(request, f"Customer “{customer.name}” updated.")
        return redirect("dashboard:customer_detail", pk=customer.pk)

    return render(
        request,
        "dashboard/form_page.html",
        {
            "form": form,
            "title": f"Edit {customer.name}",
            "eyebrow": "Enquiries & customers",
            "description": f"{customer.enquiry_count} linked enquir{'y' if customer.enquiry_count == 1 else 'ies'}.",
            "submit_label": "Save customer",
            "cancel_url": reverse("dashboard:customer_detail", args=[customer.pk]),
            "sections": form.section_fields(),
            "object": customer,
        },
    )


@staff_required
@permission_required("enquiries.delete_customer", raise_exception=True)
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    enquiry_count = customer.enquiries.count()
    if request.method == "POST":
        name = customer.name
        # Enquiries are retained; the foreign key is set to NULL.
        log_activity(
            request,
            ActivityLog.ACTION_DELETE,
            f"Customer deleted: {name} ({enquiry_count} enquiries retained)",
            target_type="enquiries.customer",
            target_id=customer.pk,
        )
        customer.delete()
        messages.success(
            request,
            f"Customer “{name}” deleted. Linked enquiries were retained without a customer record.",
        )
        return redirect("dashboard:customer_list")

    return render(
        request,
        "dashboard/confirm_delete.html",
        {
            "title": "Delete customer",
            "object_label": customer.name,
            "object_type": "customer",
            "warning": (
                f"{enquiry_count} linked enquiry record(s) will be kept but will no longer "
                "be linked to this customer. This cannot be undone."
            ),
            "cancel_url": reverse("dashboard:customer_detail", args=[customer.pk]),
        },
    )
