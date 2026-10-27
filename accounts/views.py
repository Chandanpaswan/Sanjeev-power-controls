from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash, get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.urls import reverse

from enquiries.models import Enquiry
from products.models import Product
from .forms import CustomerRegistrationForm, CustomerLoginForm, SellerRegistrationForm
from .models import CustomerProfile, SellerProfile, SellerProductAssignment, Quotation

User = get_user_model()


def is_admin(user):
    return user.is_superuser or user.is_staff


def is_approved_seller(user):
    return hasattr(user, 'seller_profile') and user.seller_profile.approval_status == SellerProfile.STATUS_APPROVED


def customer_register(request):
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Registration successful. You can now log in.')
            return redirect('accounts:login')
    else:
        form = CustomerRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


def customer_login(request):
    if request.method == 'POST':
        form = CustomerLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if form.cleaned_data.get('remember_me'):
                request.session.set_expiry(1209600)  # 2 weeks
            else:
                request.session.set_expiry(0)
            # Redirect based on role
            if is_admin(user):
                return redirect('/admin/')
            if is_approved_seller(user):
                return redirect('accounts:seller_dashboard')
            return redirect('accounts:customer_dashboard')
    else:
        form = CustomerLoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def customer_logout(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('core:home')
    return redirect('core:home')


def seller_register(request):
    if request.method == 'POST':
        form = SellerRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Seller application submitted. Awaiting admin approval.')
            return redirect('accounts:login')
    else:
        form = SellerRegistrationForm()
    return render(request, 'accounts/seller_register.html', {'form': form})


@login_required
def customer_dashboard(request):
    user = request.user
    enquiries = Enquiry.objects.filter(user=user) | Enquiry.objects.filter(email=user.email)
    enquiries = enquiries.distinct().order_by('-created_at')
    
    context = {
        'total_enquiries': enquiries.count(),
        'new_enquiries': enquiries.filter(status='new').count(),
        'in_progress_enquiries': enquiries.filter(status__in=['contacted', 'qualified', 'follow_up']).count(),
        'quotations_received': Quotation.objects.filter(customer=user).count(),
        'closed_enquiries': enquiries.filter(status__in=['closed', 'converted']).count(),
        'recent_enquiries': enquiries[:5],
    }
    return render(request, 'accounts/customer_dashboard.html', context)


@login_required
def customer_profile(request):
    user = request.user
    if request.method == 'POST':
        user.full_name = request.POST.get('full_name', '')
        user.phone = request.POST.get('phone', '')
        user.company_name = request.POST.get('company_name', '')
        user.email = request.POST.get('email', user.email).lower()
        user.username = user.email
        user.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('accounts:customer_profile')
    return render(request, 'accounts/customer_profile.html', {'user': user})


@login_required
def customer_enquiries(request):
    user = request.user
    enquiries = (Enquiry.objects.filter(user=user) | Enquiry.objects.filter(email=user.email)).distinct().order_by('-created_at')
    return render(request, 'accounts/customer_enquiries.html', {'enquiries': enquiries})


@login_required
def customer_enquiry_detail(request, pk):
    user = request.user
    enquiry = get_object_or_404(Enquiry, pk=pk)
    if enquiry.user != user and enquiry.email != user.email:
        messages.error(request, 'You do not have permission to view this enquiry.')
        return redirect('accounts:customer_enquiries')
    return render(request, 'accounts/customer_enquiry_detail.html', {'enquiry': enquiry})


@login_required
def customer_quotations(request):
    quotations = Quotation.objects.filter(customer=request.user).order_by('-created_at')
    return render(request, 'accounts/customer_quotations.html', {'quotations': quotations})


@login_required
def customer_settings(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully.')
            return redirect('accounts:customer_settings')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'accounts/customer_settings.html', {'form': form})


@login_required
@user_passes_test(is_approved_seller)
def seller_dashboard(request):
    seller_profile = request.user.seller_profile
    assignments = seller_profile.assignments.all()
    assigned_enquiries = Enquiry.objects.filter(assigned_seller=seller_profile)
    
    context = {
        'assigned_products': assignments.count(),
        'active_listings': assignments.filter(product__active=True).count(),
        'assigned_enquiries': assigned_enquiries.count(),
        'pending_quotations': Quotation.objects.filter(prepared_by=request.user, status=Quotation.STATUS_DRAFT).count(),
        'open_followups': assigned_enquiries.filter(status__in=['follow_up', 'contacted']).count(),
        'recent_enquiries': assigned_enquiries[:5],
    }
    return render(request, 'accounts/seller_dashboard.html', context)


@login_required
@user_passes_test(is_approved_seller)
def seller_products(request):
    seller_profile = request.user.seller_profile
    assignments = seller_profile.assignments.all()
    return render(request, 'accounts/seller_products.html', {'assignments': assignments})


@login_required
@user_passes_test(is_approved_seller)
def seller_enquiries(request):
    seller_profile = request.user.seller_profile
    enquiries = Enquiry.objects.filter(assigned_seller=seller_profile).order_by('-created_at')
    return render(request, 'accounts/seller_enquiries.html', {'enquiries': enquiries})


@login_required
@user_passes_test(is_approved_seller)
def seller_quotations(request):
    quotations = Quotation.objects.filter(prepared_by=request.user).order_by('-created_at')
    return render(request, 'accounts/seller_quotations.html', {'quotations': quotations})


@login_required
@user_passes_test(is_approved_seller)
def seller_profile_view(request):
    return render(request, 'accounts/seller_profile.html', {'seller_profile': request.user.seller_profile})


seller_profile = seller_profile_view


@login_required
@user_passes_test(is_admin)
def admin_users(request):
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'accounts/admin_users.html', {'users': users})


@login_required
@user_passes_test(is_admin)
def admin_customers(request):
    customers = User.objects.filter(is_staff=False).order_by('-date_joined')
    return render(request, 'accounts/admin_customers.html', {'customers': customers})


@login_required
@user_passes_test(is_admin)
def admin_sellers(request):
    sellers = SellerProfile.objects.all().order_by('-created_at')
    return render(request, 'accounts/admin_sellers.html', {'sellers': sellers})


@login_required
@user_passes_test(is_admin)
def admin_approve_seller(request, pk):
    if request.method == 'POST':
        seller = get_object_or_404(SellerProfile, pk=pk)
        seller.approval_status = SellerProfile.STATUS_APPROVED
        seller.approved_by = request.user
        seller.approved_at = timezone.now()
        seller.save()
        messages.success(request, f'{seller.business_name} approved successfully.')
    return redirect('accounts:admin_sellers')


@login_required
@user_passes_test(is_admin)
def admin_reject_seller(request, pk):
    if request.method == 'POST':
        seller = get_object_or_404(SellerProfile, pk=pk)
        seller.approval_status = SellerProfile.STATUS_REJECTED
        seller.approved_by = request.user
        seller.approved_at = timezone.now()
        seller.save()
        messages.success(request, f'{seller.business_name} rejected.')
    return redirect('accounts:admin_sellers')


@login_required
@user_passes_test(is_admin)
def admin_enquiries(request):
    enquiries = Enquiry.objects.all().order_by('-created_at')
    sellers = SellerProfile.objects.filter(approval_status=SellerProfile.STATUS_APPROVED)
    if request.method == 'POST':
        enquiry_id = request.POST.get('enquiry_id')
        seller_id = request.POST.get('seller_id')
        if enquiry_id and seller_id:
            enquiry = get_object_or_404(Enquiry, pk=enquiry_id)
            seller = get_object_or_404(SellerProfile, pk=seller_id)
            enquiry.assigned_seller = seller
            enquiry.save()
            messages.success(request, 'Enquiry assigned to seller.')
    return render(request, 'accounts/admin_enquiries.html', {'enquiries': enquiries, 'sellers': sellers})


@login_required
@user_passes_test(is_admin)
def admin_quotations(request):
    quotations = Quotation.objects.all().order_by('-created_at')
    return render(request, 'accounts/admin_quotations.html', {'quotations': quotations})


@login_required
@user_passes_test(is_admin)
def admin_create_quotation(request):
    if request.method == 'POST':
        # Basic creation
        enquiry = get_object_or_404(Enquiry, pk=request.POST.get('enquiry_id'))
        customer = enquiry.user if enquiry.user else User.objects.filter(email=enquiry.email).first()
        if not customer:
            messages.error(request, 'No customer account found.')
            return redirect('accounts:admin_quotations')
        quotation = Quotation.objects.create(
            enquiry=enquiry,
            customer=customer,
            prepared_by=request.user,
            product=enquiry.product,
            quantity=enquiry.quantity if enquiry.quantity else request.POST.get('quantity'),
            unit_price=request.POST.get('unit_price') or 0,
            taxes=request.POST.get('taxes') or 0,
            discount=request.POST.get('discount') or 0,
            validity_date=request.POST.get('validity_date') or None,
            terms_and_conditions=request.POST.get('terms_and_conditions', ''),
            status=Quotation.STATUS_DRAFT,
        )
        messages.success(request, f'Quotation {quotation.quotation_number} created.')
        return redirect('accounts:admin_quotations')
    
    enquiries = Enquiry.objects.all()
    return render(request, 'accounts/admin_create_quotation.html', {'enquiries': enquiries})
