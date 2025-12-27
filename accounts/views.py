from django.contrib import messages
from django.contrib.auth import update_session_auth_hash,login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.utils.decorators import method_decorator
from django.views.generic import CreateView,FormView
from django_filters.views import FilterView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.urls import reverse_lazy, reverse
from django.views import View
from django.utils.translation import gettext_lazy as _
from xhtml2pdf import pisa

from django.core.paginator import Paginator
from django.db.models import Q, Count
from accounts.forms import CustomAuthenticationForm, FirstTimeSetupForm
from accounts.models import User
from accounts.decorators import admin_required
from accounts.filters import LecturerFilter, StudentFilter
from accounts.forms import (
    ParentAddForm,
    ProfileUpdateForm,
    ProgramUpdateForm,
    StaffAddForm,
    StudentAddForm,
)
from accounts.models import Parent, Student, User
from core.models import Semester, Session
from course.models import Course
from result.models import TakenCourse

class CustomLoginView(DjangoLoginView):
    """
    Custom login view that checks for first-time login.
    
    Flow:
    1. User submits credentials
    2. If auth fails → show error
    3. If auth succeeds and is_first_login=True → redirect to setup
    4. If auth succeeds and is_first_login=False → login normally
    """
    form_class = CustomAuthenticationForm
    template_name = 'registration/login.html'
    redirect_authenticated_user = True
    
    def form_valid(self, form):
        """
        Override to check for first-time login before logging in.
        """
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password')
        
        # Authenticate user
        user = authenticate(self.request, username=username, password=password)
        
        if user is not None:
            # Check if this is first time login
            if user.is_first_login:
                # Store user_id in session for first-time setup
                self.request.session['first_time_user_id'] = user.id
                messages.info(
                    self.request,
                    _("Welcome! Please complete your profile setup to continue.")
                )
                return redirect('first_time_setup')
            
            # Normal login for returning users
            login(self.request, user)
            messages.success(self.request, _("Welcome back, {}!").format(user.get_full_name))
            return redirect(self.get_success_url())
        
        # This shouldn't happen if form validation passed, but as a safety
        form.add_error(None, _("Authentication failed."))
        return self.form_invalid(form)
    
    def get_success_url(self):
        """
        Redirect to dashboard after successful login.
        """
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse('home')  # or 'dashboard'


class FirstTimeSetupView(FormView):
    """
    View for first-time users to set up their account.
    
    Security:
    - Only accessible after successful authentication
    - User ID stored in session (not logged in yet)
    - Cannot be accessed if is_first_login=False
    """
    template_name = 'registration/first_time_login.html'
    form_class = FirstTimeSetupForm
    success_url = reverse_lazy('home')  # or 'dashboard'
    
    def dispatch(self, request, *args, **kwargs):
        """
        Check if user is eligible for first-time setup.
        """
        # Get user_id from session
        user_id = request.session.get('first_time_user_id')
        
        if not user_id:
            messages.error(request, _("Invalid access. Please login first."))
            return redirect('login')
        
        # Get user object
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, _("User not found."))
            return redirect('login')
        
        # Check if user has already completed setup
        if not user.is_first_login:
            messages.info(request, _("You have already completed the setup."))
            return redirect('login')
        
        # Store user in instance for later use
        self.current_user = user
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        """
        Pass user instance to form.
        """
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.current_user
        return kwargs
    
    def get_context_data(self, **kwargs):
        """
        Add user info to context for template.
        """
        context = super().get_context_data(**kwargs)
        context['user'] = self.current_user
        context['title'] = _("Complete Your Profile Setup")
        return context
    
    def form_valid(self, form):
        """
        Save new credentials and log user in.
        """
        # Save form (updates username, password, and is_first_login)
        user = form.save()
        
        # Clear the session variable
        if 'first_time_user_id' in self.request.session:
            del self.request.session['first_time_user_id']
        
        # Log the user in
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        messages.success(
            self.request,
            _("Your profile has been set up successfully! Welcome to the system.")
        )
        
        return super().form_valid(form)
    
    def form_invalid(self, form):
        """
        Show error message on form validation failure.
        """
        messages.error(
            self.request,
            _("Please correct the errors below.")
        )
        return super().form_invalid(form)

@login_required
@admin_required
def users_dashboard(request):
    """
    Main users dashboard view.
    Displays statistics and user management interface.
    """
    # Get user statistics
    stats = {
        'total_users': User.objects.count(),
        'students': User.objects.filter(is_student=True).count(),
        'lecturers': User.objects.filter(is_lecturer=True).count(),
        'admins': User.objects.filter(is_superuser=True).count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'inactive_users': User.objects.filter(is_active=False).count(),
        'first_login_pending': User.objects.filter(is_first_login=True).count(),
    }
    
    context = {
        'title': _('Users Dashboard'),
        'stats': stats,
    }
    
    return render(request, 'accounts/users_dashboard.html', context)


@login_required
@admin_required
def users_list_ajax(request):
    """
    AJAX endpoint to fetch users list with filtering, search, and pagination.
    
    Query Parameters:
    - search: Search term for username, email, or name
    - role: Filter by role (student, lecturer, admin)
    - status: Filter by status (active, inactive)
    - first_login: Filter by first login status (pending, completed)
    - page: Page number for pagination
    - per_page: Items per page (default: 10)
    """
    
    # Get query parameters
    search = request.GET.get('search', '').strip()
    role = request.GET.get('role', '')
    status = request.GET.get('status', '')
    first_login = request.GET.get('first_login', '')
    page = request.GET.get('page', 1)
    per_page = int(request.GET.get('per_page', 10))
    
    # Start with all users
    users = User.objects.all()
    
    # Apply search filter
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    # Apply role filter
    if role == 'student':
        users = users.filter(is_student=True)
    elif role == 'lecturer':
        users = users.filter(is_lecturer=True)
    elif role == 'admin':
        users = users.filter(is_superuser=True)
    
    # Apply status filter
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)
    
    # Apply first login filter
    if first_login == 'pending':
        users = users.filter(is_first_login=True)
    elif first_login == 'completed':
        users = users.filter(is_first_login=False)
    
    # Order by date joined (newest first)
    users = users.order_by('-date_joined')
    
    # Get total count before pagination
    total_count = users.count()
    
    # Paginate
    paginator = Paginator(users, per_page)
    try:
        users_page = paginator.page(page)
    except:
        users_page = paginator.page(1)
    
    # Prepare user data
    users_data = []
    for user in users_page:
        users_data.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name,
            'email': user.email or 'N/A',
            'role': 'User',
            'is_active': user.is_active,
            'is_first_login': user.is_first_login,
            'date_joined': user.date_joined.strftime('%b %d, %Y'),
            'last_login': user.last_login.strftime('%b %d, %Y %H:%M') if user.last_login else 'Never',
            'picture_url': user.get_picture(),
            'profile_url': user.get_absolute_url(),
        })
    
    # Prepare response
    response_data = {
        'users': users_data,
        'pagination': {
            'current_page': users_page.number,
            'total_pages': paginator.num_pages,
            'total_count': total_count,
            'has_previous': users_page.has_previous(),
            'has_next': users_page.has_next(),
            'per_page': per_page,
        },
        'filters': {
            'search': search,
            'role': role,
            'status': status,
            'first_login': first_login,
        }
    }
    
    return JsonResponse(response_data)


@login_required
@admin_required
def user_quick_actions_ajax(request, user_id):
    """
    AJAX endpoint for quick actions on users.
    
    Actions:
    - toggle_active: Toggle user active status
    - reset_first_login: Reset first login status
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)
    
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'}, status=404)
    
    action = request.POST.get('action')
    
    if action == 'toggle_active':
        user.is_active = not user.is_active
        user.save()
        return JsonResponse({
            'success': True,
            'message': f'User {"activated" if user.is_active else "deactivated"} successfully',
            'is_active': user.is_active
        })
    
    elif action == 'reset_first_login':
        user.is_first_login = True
        user.save()
        return JsonResponse({
            'success': True,
            'message': 'User will be required to complete first-time setup on next login',
            'is_first_login': user.is_first_login
        })
    
    else:
        return JsonResponse({'success': False, 'message': 'Invalid action'}, status=400)

# ########################################################
# Utility Functions
# ########################################################


def render_to_pdf(template_name, context):
    """Render a given template to PDF format."""
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="profile.pdf"'
    template = render_to_string(template_name, context)
    pdf = pisa.CreatePDF(template, dest=response)
    if pdf.err:
        return HttpResponse("We had some problems generating the PDF")
    return response


# ########################################################
# Authentication and Registration
# ########################################################


def validate_username(request):
    username = request.GET.get("username", None)
    data = {"is_taken": User.objects.filter(username__iexact=username).exists()}
    return JsonResponse(data)


def register(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully.")
            return redirect("login")
        messages.error(
            request, "Something is not correct, please fill all fields correctly."
        )
    else:
        form = StudentAddForm()
    return render(request, "registration/register.html", {"form": form})


# ########################################################
# Profile Views
# ########################################################


@login_required
def profile(request):
    """Show profile of the current user."""
    current_session = Session.objects.filter(is_current_session=True).first()
    current_semester = Semester.objects.filter(
        is_current_semester=True, session=current_session
    ).first()

    context = {
        "title": request.user.get_full_name,
        "current_session": current_session,
        "current_semester": current_semester,
    }

    if request.user.is_lecturer:
        courses = Course.objects.filter(
            allocated_course__lecturer__pk=request.user.id, semester=current_semester
        )
        context["courses"] = courses
        return render(request, "accounts/profile.html", context)

    if request.user.is_student:
        student = get_object_or_404(Student, student__pk=request.user.id)
        parent = Parent.objects.filter(student=student).first()
        courses = TakenCourse.objects.filter(
            student__student__id=request.user.id, course__level=student.level
        )
        context.update(
            {
                "parent": parent,
                "courses": courses,
                "level": student.level,
            }
        )
        return render(request, "accounts/profile.html", context)

    # For superuser or other staff
    staff = User.objects.filter(is_lecturer=True)
    context["staff"] = staff
    return render(request, "accounts/profile.html", context)


@login_required
@admin_required
def profile_single(request, user_id):
    """Show profile of any selected user."""
    if request.user.id == user_id:
        return redirect("profile")

    current_session = Session.objects.filter(is_current_session=True).first()
    current_semester = Semester.objects.filter(
        is_current_semester=True, session=current_session
    ).first()
    user = get_object_or_404(User, pk=user_id)

    context = {
        "title": user.get_full_name,
        "user": user,
        "current_session": current_session,
        "current_semester": current_semester,
    }

    if user.is_lecturer:
        courses = Course.objects.filter(
            allocated_course__lecturer__pk=user_id, semester=current_semester
        )
        context.update(
            {
                "user_type": "Lecturer",
                "courses": courses,
            }
        )
    elif user.is_student:
        student = get_object_or_404(Student, student__pk=user_id)
        courses = TakenCourse.objects.filter(
            student__student__id=user_id, course__level=student.level
        )
        context.update(
            {
                "user_type": "Student",
                "courses": courses,
                "student": student,
            }
        )
    else:
        context["user_type"] = "Superuser"

    if request.GET.get("download_pdf"):
        return render_to_pdf("pdf/profile_single.html", context)

    return render(request, "accounts/profile_single.html", context)


@login_required
@admin_required
def admin_panel(request):
    return render(request, "setting/admin_panel.html", {"title": "Admin Panel"})


# ########################################################
# Settings Views
# ########################################################


@login_required
def profile_update(request):
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("profile")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(request, "setting/profile_info_change.html", {"form": form})


@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password was successfully updated!")
            return redirect("profile")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "setting/password_change.html", {"form": form})


# ########################################################
# Staff (Lecturer) Views
# ########################################################


@login_required
@admin_required
def staff_add_view(request):
    if request.method == "POST":
        form = StaffAddForm(request.POST)
        if form.is_valid():
            lecturer = form.save()
            full_name = lecturer.get_full_name
            email = lecturer.email
            messages.success(
                request,
                f"Account for lecturer {full_name} has been created. "
                f"An email with account credentials will be sent to {email} within a minute.",
            )
            return redirect("lecturer_list")
    else:
        form = StaffAddForm()
    return render(
        request, "accounts/add_staff.html", {"title": "Add Lecturer", "form": form}
    )


@login_required
@admin_required
def edit_staff(request, pk):
    lecturer = get_object_or_404(User, is_lecturer=True, pk=pk)
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=lecturer)
        if form.is_valid():
            form.save()
            full_name = lecturer.get_full_name
            messages.success(request, f"Lecturer {full_name} has been updated.")
            return redirect("lecturer_list")
        messages.error(request, "Please correct the error below.")
    else:
        form = ProfileUpdateForm(instance=lecturer)
    return render(
        request, "accounts/edit_lecturer.html", {"title": "Edit Lecturer", "form": form}
    )


@method_decorator([login_required, admin_required], name="dispatch")
class LecturerFilterView(FilterView):
    filterset_class = LecturerFilter
    queryset = User.objects.filter(is_lecturer=True)
    template_name = "accounts/lecturer_list.html"
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Lecturers"
        return context


@login_required
@admin_required
def render_lecturer_pdf_list(request):
    lecturers = User.objects.filter(is_lecturer=True)
    template_path = "pdf/lecturer_list.html"
    context = {"lecturers": lecturers}
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="lecturers_list.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse(f"We had some errors <pre>{html}</pre>")
    return response


@login_required
@admin_required
def delete_staff(request, pk):
    lecturer = get_object_or_404(User, is_lecturer=True, pk=pk)
    full_name = lecturer.get_full_name
    lecturer.delete()
    messages.success(request, f"Lecturer {full_name} has been deleted.")
    return redirect("lecturer_list")


# ########################################################
# Student Views
# ########################################################


@login_required
@admin_required
def student_add_view(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST)
        if form.is_valid():
            student = form.save()
            full_name = student.get_full_name
            email = student.email
            messages.success(
                request,
                f"Account for {full_name} has been created. "
                f"An email with account credentials will be sent to {email} within a minute.",
            )
            return redirect("student_list")
        messages.error(request, "Correct the error(s) below.")
    else:
        form = StudentAddForm()
    return render(
        request, "accounts/add_student.html", {"title": "Add Student", "form": form}
    )


@login_required
@admin_required
def edit_student(request, pk):
    student_user = get_object_or_404(User, is_student=True, pk=pk)
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=student_user)
        if form.is_valid():
            form.save()
            full_name = student_user.get_full_name
            messages.success(request, f"Student {full_name} has been updated.")
            return redirect("student_list")
        messages.error(request, "Please correct the error below.")
    else:
        form = ProfileUpdateForm(instance=student_user)
    return render(
        request, "accounts/edit_student.html", {"title": "Edit Student", "form": form}
    )


@method_decorator([login_required, admin_required], name="dispatch")
class StudentListView(FilterView):
    queryset = Student.objects.all()
    filterset_class = StudentFilter
    template_name = "accounts/student_list.html"
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Students"
        return context


@login_required
@admin_required
def render_student_pdf_list(request):
    students = Student.objects.all()
    template_path = "pdf/student_list.html"
    context = {"students": students}
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="students_list.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse(f"We had some errors <pre>{html}</pre>")
    return response


@login_required
@admin_required
def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    full_name = student.student.get_full_name
    student.delete()
    messages.success(request, f"Student {full_name} has been deleted.")
    return redirect("student_list")


@login_required
@admin_required
def edit_student_program(request, pk):
    student = get_object_or_404(Student, student_id=pk)
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = ProgramUpdateForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            full_name = user.get_full_name
            messages.success(request, f"{full_name}'s program has been updated.")
            return redirect("profile_single", user_id=pk)
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = ProgramUpdateForm(instance=student)
    return render(
        request,
        "accounts/edit_student_program.html",
        {"title": "Edit Program", "form": form, "student": student},
    )


# ########################################################
# Parent Views
# ########################################################


@method_decorator([login_required, admin_required], name="dispatch")
class ParentAdd(CreateView):
    model = Parent
    form_class = ParentAddForm
    template_name = "accounts/parent_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Parent added successfully.")
        return super().form_valid(form)
