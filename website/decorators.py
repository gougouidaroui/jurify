from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponseForbidden


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, 'Veuillez vous connecter pour accéder à cette page.')
                return redirect('login')
            if request.user.role not in roles:
                return HttpResponseForbidden(
                    '<h1>403 Accès Interdit</h1>'
                    '<p>Vous n\'avez pas les permissions nécessaires pour accéder à cette page.</p>'
                )
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def admin_required(view_func):
    return role_required('ADMIN')(view_func)


def jury_required(view_func):
    return role_required('JURY', 'PRESIDENT_JURY', 'ADMIN')(view_func)


def president_jury_required(view_func):
    return role_required('PRESIDENT_JURY', 'ADMIN')(view_func)


def student_required(view_func):
    return role_required('STUDENT')(view_func)
