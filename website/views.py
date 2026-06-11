from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponseForbidden, HttpResponse
from django.forms import formset_factory
from django.template.loader import render_to_string
import csv
from rest_framework_simplejwt.tokens import RefreshToken
from .forms import (
    SignUpForm, EmailAuthenticationForm, CustomPasswordChangeForm,
    UserProfileForm, ProjectForm, ProjectAdminForm,
    SessionForm, CritereForm, CritereFormSet, JuryAssignForm,
    ProjectAssignForm, SessionOpenForm, VoteForm,
)
from .models import CustomUser, LoginHistory, Projet, SessionVote, Critere, Vote, Resultat, Rapport, Notification, ActionLog, create_notification, log_action
from .decorators import role_required


def set_auth_cookies(response, user):
    refresh = RefreshToken.for_user(user)
    response.set_cookie(
        key=settings.JWT_AUTH_COOKIE,
        value=str(refresh.access_token),
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        max_age=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(),
    )
    response.set_cookie(
        key=settings.JWT_AUTH_REFRESH_COOKIE,
        value=str(refresh),
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds(),
    )


def clear_auth_cookies(response):
    response.delete_cookie(settings.JWT_AUTH_COOKIE)
    response.delete_cookie(settings.JWT_AUTH_REFRESH_COOKIE)


def home(request):
    return render(request, 'home.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            log_action(user, ActionLog.Action.CREATE, model_name='CustomUser', object_id=user.pk, details='Inscription')
            response = redirect('home')
            set_auth_cookies(response, user)
            messages.success(request, 'Inscription réussie ! Bienvenue sur Jurify.')
            return response
    else:
        form = SignUpForm()

    return render(request, 'register.html', {'form': form, 'title': 'Inscription'})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = EmailAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            ip = request.META.get('REMOTE_ADDR', '')
            LoginHistory.objects.create(
                user=user,
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
            log_action(user, ActionLog.Action.LOGIN, ip_address=ip)

            response = redirect('home')
            set_auth_cookies(response, user)
            messages.success(request, f'Bon retour, {user.get_full_name() or user.email} !')
            return response
    else:
        form = EmailAuthenticationForm()

    return render(request, 'login.html', {'form': form, 'title': 'Connexion'})


def logout_view(request):
    logout(request)
    response = redirect('home')
    clear_auth_cookies(response)
    messages.success(request, 'Vous avez été déconnecté.')
    return response


def refresh_token_view(request):
    refresh_token = request.COOKIES.get(settings.JWT_AUTH_REFRESH_COOKIE)
    if not refresh_token:
        return redirect('login')

    from rest_framework_simplejwt.exceptions import TokenError
    try:
        refresh = RefreshToken(refresh_token)
        user = CustomUser.objects.get(id=refresh['user_id'])
        response = redirect(request.META.get('HTTP_REFERER', 'home'))
        set_auth_cookies(response, user)
        return response
    except (TokenError, CustomUser.DoesNotExist):
        response = redirect('login')
        clear_auth_cookies(response)
        return response


@role_required('ADMIN', 'JURY', 'PRESIDENT_JURY', 'STUDENT')
def profile_view(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profil mis à jour avec succès.')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'profile.html', {
        'form': form,
        'title': 'Mon Profil',
        'login_history': request.user.login_history.all()[:10],
    })


@role_required('ADMIN', 'JURY', 'PRESIDENT_JURY', 'STUDENT')
def password_change_view(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Mot de passe modifié avec succès.')
            return redirect('profile')
    else:
        form = CustomPasswordChangeForm(request.user)

    return render(request, 'password_change.html', {
        'form': form,
        'title': 'Changer le mot de passe',
    })


@role_required('ADMIN', 'STUDENT')
def project_list_view(request):
    if request.user.role == 'ADMIN':
        projets = Projet.objects.all()
    else:
        projets = Projet.objects.filter(student=request.user)

    filiere = request.GET.get('filiere')
    status = request.GET.get('status')
    search = request.GET.get('search')

    if filiere:
        projets = projets.filter(filiere=filiere)
    if status:
        projets = projets.filter(status=status)
    if search:
        projets = projets.filter(title__icontains=search)

    return render(request, 'project_list.html', {
        'projets': projets,
        'title': 'Mes Projets' if request.user.role == 'STUDENT' else 'Gestion des Projets',
        'current_filiere': filiere,
        'current_status': status,
        'projet_model': Projet,
    })


@role_required('STUDENT')
def project_create_view(request):
    if request.user.role != 'STUDENT':
        return HttpResponseForbidden()

    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES)
        form.instance._owner_email = request.user.email
        if form.is_valid():
            projet = form.save(commit=False)
            projet.student = request.user
            projet.status = Projet.Status.DRAFT
            projet.save()
            messages.success(request, 'Projet créé avec succès. Vous pouvez maintenant le soumettre.')
            return redirect('project_detail', pk=projet.pk)
    else:
        form = ProjectForm()

    return render(request, 'project_form.html', {
        'form': form,
        'title': 'Nouveau Projet',
        'submit_label': 'Enregistrer le projet',
    })


@role_required('ADMIN', 'STUDENT')
def project_detail_view(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    if request.user.role == 'STUDENT' and projet.student != request.user:
        return HttpResponseForbidden()
    team_members_display = []
    if projet.team_members:
        members = CustomUser.objects.filter(email__in=projet.team_members)
        team_members_display = [{
            'name': m.get_full_name() or m.email,
            'email': m.email,
        } for m in members]
    return render(request, 'project_detail.html', {
        'projet': projet,
        'title': projet.title,
        'can_edit': projet.can_edit(request.user),
        'team_members_display': team_members_display,
    })


@role_required('STUDENT')
def project_edit_view(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    if not projet.can_edit(request.user):
        messages.error(request, 'Ce projet ne peut plus être modifié.')
        return redirect('project_detail', pk=projet.pk)

    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES, instance=projet)
        form.instance._owner_email = projet.student.email
        if form.is_valid():
            form.save()
            messages.success(request, 'Projet mis à jour avec succès.')
            return redirect('project_detail', pk=projet.pk)
    else:
        form = ProjectForm(instance=projet)

    return render(request, 'project_form.html', {
        'form': form,
        'title': 'Modifier le Projet',
        'submit_label': 'Enregistrer les modifications',
        'projet': projet,
    })


@role_required('STUDENT')
def project_submit_view(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    if projet.student != request.user:
        return HttpResponseForbidden()
    if projet.status != Projet.Status.DRAFT:
        messages.error(request, 'Ce projet a déjà été soumis.')
        return redirect('project_detail', pk=projet.pk)

    if request.method == 'POST':
        projet.status = Projet.Status.SUBMITTED
        projet.submitted_at = timezone.now()
        projet.save(update_fields=['status', 'submitted_at'])
        messages.success(request, 'Projet soumis avec succès ! Un accusé de réception a été généré.')
        return redirect('project_detail', pk=projet.pk)

    return render(request, 'project_confirm_submit.html', {
        'projet': projet,
        'title': 'Confirmer la soumission',
    })


@role_required('ADMIN')
def project_validate_view(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    if projet.status != Projet.Status.SUBMITTED:
        messages.error(request, 'Seuls les projets soumis peuvent être validés ou rejetés.')
        return redirect('project_detail', pk=projet.pk)

    if request.method == 'POST':
        form = ProjectAdminForm(request.POST, instance=projet)
        if form.is_valid():
            projet = form.save(commit=False)
            if projet.status == Projet.Status.VALIDATED:
                projet.validated_at = timezone.now()
                projet.validated_by = request.user
            elif projet.status == Projet.Status.REJECTED:
                if not projet.rejection_reason:
                    messages.error(request, 'Un motif de rejet est obligatoire.')
                    return render(request, 'project_validate.html', {
                        'form': form, 'projet': projet, 'title': 'Valider / Rejeter'
                    })
                projet.validated_at = None
                projet.validated_by = request.user
            projet.save()
            log_action(request.user, ActionLog.Action.VALIDATE, model_name='Projet',
                       object_id=projet.pk, details=f'Projet {dict(Projet.Status.choices)[projet.status]}: {projet.title}')
            notif_type = Notification.Type.PROJECT_VALIDATED if projet.status == 'VALIDATED' else Notification.Type.PROJECT_REJECTED
            create_notification(
                projet.student, notif_type,
                f'Votre projet "{projet.title}" a été {dict(Projet.Status.choices)[projet.status].lower()}.',
                lien=reverse('project_detail', args=[projet.pk]),
            )
            status_display = dict(Projet.Status.choices)[projet.status]
            messages.success(request, f'Projet "{projet.title}" {status_display.lower()}.')
            return redirect('project_detail', pk=projet.pk)
    else:
        form = ProjectAdminForm(instance=projet)

    return render(request, 'project_validate.html', {
        'form': form,
        'projet': projet,
        'title': 'Valider / Rejeter le Projet',
    })


@role_required('ADMIN')
def project_delete_view(request, pk):
    projet = get_object_or_404(Projet, pk=pk)
    if request.method == 'POST':
        projet.delete()
        messages.success(request, 'Projet supprimé avec succès.')
        return redirect('project_list')
    return render(request, 'project_confirm_delete.html', {
        'projet': projet,
        'title': 'Supprimer le Projet',
    })


@role_required('ADMIN', 'JURY', 'PRESIDENT_JURY')
def session_list_view(request):
    if request.user.role == 'ADMIN':
        sessions = SessionVote.objects.all()
    else:
        sessions = SessionVote.objects.filter(jury=request.user)
    filiere = request.GET.get('filiere')
    status = request.GET.get('status')
    if filiere:
        sessions = sessions.filter(filiere=filiere)
    if status:
        sessions = sessions.filter(status=status)
    return render(request, 'session_list.html', {
        'sessions': sessions,
        'title': 'Sessions de vote',
        'current_filiere': filiere,
        'current_status': status,
        'session_vote': SessionVote,
        'projet_model': Projet,
    })


@role_required('ADMIN')
def session_create_view(request):
    if request.method == 'POST':
        form = SessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.created_by = request.user
            session.save()
            form.save_m2m()
            messages.success(request, f'Session "{session.nom}" créée avec succès. Configurez maintenant les critères.')
            return redirect('session_criteria', pk=session.pk)
    else:
        form = SessionForm()

    return render(request, 'session_form.html', {
        'form': form,
        'title': 'Nouvelle session de vote',
        'submit_label': 'Créer la session',
    })


@role_required('ADMIN')
def session_detail_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    return render(request, 'session_detail.html', {
        'session': session,
        'title': session.nom,
    })


@role_required('ADMIN')
def session_criteria_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    CritereFormSetFactory = formset_factory(CritereForm, formset=CritereFormSet, extra=3, can_delete=True)

    if request.method == 'POST':
        formset = CritereFormSetFactory(request.POST)
        if formset.is_valid():
            Critere.objects.filter(session=session).delete()
            for form in formset:
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                    Critere.objects.create(
                        session=session,
                        nom=form.cleaned_data['nom'],
                        poids=form.cleaned_data['poids'],
                        note_max=form.cleaned_data['note_max'],
                    )
            messages.success(request, 'Critères enregistrés avec succès.')
            return redirect('session_detail', pk=session.pk)
    else:
        existing = session.criteres.all()
        initial = [{'nom': c.nom, 'poids': c.poids, 'note_max': c.note_max} for c in existing]
        extra = max(3 - len(existing), 0)
        CritereFormSetFactory = formset_factory(CritereForm, formset=CritereFormSet, extra=extra, can_delete=True)
        formset = CritereFormSetFactory(initial=initial) if initial else CritereFormSetFactory()

    return render(request, 'session_criteria.html', {
        'formset': formset,
        'session': session,
        'title': 'Configurer les critères',
    })


@role_required('ADMIN')
def session_assign_jury_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    if request.method == 'POST':
        form = JuryAssignForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            messages.success(request, 'Membres du jury affectés avec succès.')
            return redirect('session_detail', pk=session.pk)
    else:
        form = JuryAssignForm(instance=session)

    return render(request, 'session_assign_jury.html', {
        'form': form,
        'session': session,
        'title': 'Affecter les jurys',
    })


@role_required('ADMIN')
def session_assign_projets_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    if request.method == 'POST':
        form = ProjectAssignForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            messages.success(request, 'Projets affectés à la session avec succès.')
            return redirect('session_detail', pk=session.pk)
    else:
        form = ProjectAssignForm(instance=session)

    return render(request, 'session_assign_projets.html', {
        'form': form,
        'session': session,
        'title': 'Affecter les projets',
    })


@role_required('ADMIN')
def session_open_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    if session.status != SessionVote.Status.PLANNED:
        messages.error(request, 'Seules les sessions planifiées peuvent être ouvertes.')
        return redirect('session_detail', pk=session.pk)

    criteres_ok = session.criteres.exists()
    jury_ok = session.jury.exists()
    projets_ok = session.projets.exists()

    if not all([criteres_ok, jury_ok, projets_ok]):
        missing = []
        if not criteres_ok:
            missing.append('critères')
        if not jury_ok:
            missing.append('membres du jury')
        if not projets_ok:
            missing.append('projets')
        messages.error(request, f'Impossible d\'ouvrir la session. Éléments manquants : {", ".join(missing)}.')
        return redirect('session_detail', pk=session.pk)

    total_poids = sum(c.poids for c in session.criteres.all())
    if total_poids != 100:
        messages.error(request, f'La somme des poids des critères doit être 100% (actuellement: {total_poids}%).')
        return redirect('session_criteria', pk=session.pk)

    if request.method == 'POST':
        form = SessionOpenForm(request.POST)
        if form.is_valid() and form.cleaned_data['confirm']:
            session.status = SessionVote.Status.OPEN
            session.save(update_fields=['status'])
            log_action(request.user, ActionLog.Action.UPDATE, model_name='SessionVote',
                       object_id=session.pk, details=f'Session ouverte: {session.nom}')
            for jury in session.jury.all():
                create_notification(
                    jury, Notification.Type.VOTE_OPEN,
                    f'La session "{session.nom}" est ouverte. Vous pouvez voter.',
                    lien=reverse('voting_dashboard'),
                )
            messages.success(request, f'Session "{session.nom}" ouverte ! Les jurys peuvent maintenant voter.')
            return redirect('session_detail', pk=session.pk)
    else:
        form = SessionOpenForm()

    return render(request, 'session_open_confirm.html', {
        'form': form,
        'session': session,
        'title': 'Ouvrir la session',
    })


@role_required('JURY', 'PRESIDENT_JURY')
def voting_dashboard_view(request):
    base_qs = SessionVote.objects.filter(jury=request.user)
    filiere = request.GET.get('filiere')
    status = request.GET.get('status')
    if filiere:
        base_qs = base_qs.filter(filiere=filiere)
    if status:
        base_qs = base_qs.filter(status=status)

    active_sessions = base_qs.filter(status=SessionVote.Status.OPEN).prefetch_related('projets', 'projets__student')
    voted_sessions = base_qs.filter(status__in=[SessionVote.Status.CLOSED, SessionVote.Status.PUBLISHED])

    for session in active_sessions:
        votes_qs = Vote.objects.filter(jury=request.user, session=session)
        vote_map = {v.projet_id: v for v in votes_qs}
        for projet in session.projets.all():
            projet.user_vote = vote_map.get(projet.pk)

    return render(request, 'voting_dashboard.html', {
        'active_sessions': active_sessions,
        'voted_sessions': voted_sessions,
        'session_vote': SessionVote,
        'projet_model': Projet,
        'current_filiere': request.GET.get('filiere'),
        'current_status': request.GET.get('status'),
        'title': 'Voter',
    })


@role_required('JURY', 'PRESIDENT_JURY')
def vote_project_view(request, session_pk, projet_pk):
    session = get_object_or_404(SessionVote, pk=session_pk, jury=request.user)
    projet = get_object_or_404(Projet, pk=projet_pk, sessions=session)

    if session.status != SessionVote.Status.OPEN:
        messages.error(request, 'Cette session n\'est pas ouverte au vote.')
        return redirect('voting_dashboard')

    existing_vote = Vote.objects.filter(jury=request.user, projet=projet, session=session).first()

    if request.method == 'POST':
        form = VoteForm(
            request.POST,
            session=session,
            projet=projet,
            existing_vote=existing_vote,
        )
        if form.is_valid():
            vote = form.save(
                jury=request.user,
                ip_address=request.META.get('REMOTE_ADDR', ''),
            )
            action = ActionLog.Action.UPDATE if existing_vote else ActionLog.Action.VOTE
            log_action(request.user, action, model_name='Vote',
                       object_id=vote.pk, details=f'{projet.title}: {vote.score_total}',
                       ip_address=request.META.get('REMOTE_ADDR', ''))
            if existing_vote:
                messages.success(request, f'Vote modifié pour "{projet.title}". Score: {vote.score_total}')
            else:
                messages.success(request, f'Vote enregistré pour "{projet.title}". Score: {vote.score_total}')
            return redirect('voting_dashboard')
    else:
        form = VoteForm(session=session, projet=projet, existing_vote=existing_vote)

    return render(request, 'vote_form.html', {
        'form': form,
        'session': session,
        'projet': projet,
        'existing_vote': existing_vote,
        'title': f'Voter — {projet.title}',
    })


@role_required('JURY', 'PRESIDENT_JURY')
def vote_session_summary_view(request, session_pk):
    session = get_object_or_404(SessionVote, pk=session_pk, jury=request.user)
    votes = Vote.objects.filter(jury=request.user, session=session).select_related('projet').prefetch_related('notes__critere')

    return render(request, 'vote_summary.html', {
        'session': session,
        'votes': votes,
        'title': f'Mes votes — {session.nom}',
        'projets_total': session.projets.count(),
        'votes_count': votes.count(),
    })


@role_required('PRESIDENT_JURY', 'ADMIN')
def session_close_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    if request.user.role != 'ADMIN' and request.user not in session.jury.all():
        return HttpResponseForbidden()

    if session.status != SessionVote.Status.OPEN:
        messages.error(request, 'Seules les sessions ouvertes peuvent être fermées.')
        return redirect('session_detail', pk=session.pk)

    all_voted, missing_jury = session.all_jury_voted()
    if not all_voted:
        missing_count = len(missing_jury)
        messages.error(
            request,
            f'Clôture refusée — {missing_count} membre(s) du jury n\'ont pas encore voté.'
        )
        return redirect('session_detail', pk=session.pk)

    if request.method == 'POST':
        session.calculer_resultats()
        session.status = SessionVote.Status.CLOSED
        session.closed_at = timezone.now()
        session.closed_by = request.user
        session.save(update_fields=['status', 'closed_at', 'closed_by'])
        log_action(request.user, ActionLog.Action.CLOSE, model_name='SessionVote',
                   object_id=session.pk, details=f'Session fermée: {session.nom}')
        for jury in session.jury.all():
            create_notification(
                jury, Notification.Type.VOTE_CLOSED,
                f'La session "{session.nom}" est fermée. Les résultats sont en cours de validation.',
                lien=reverse('session_results', args=[session.pk]),
            )
        messages.success(request, f'Session "{session.nom}" fermée. Les résultats ont été calculés.')
        return redirect('session_results', pk=session.pk)

    jury_votes_count = session.votes.values('jury').distinct().count()
    projets_count = session.projets.count()
    total_votes = session.votes.count()

    return render(request, 'session_close_confirm.html', {
        'session': session,
        'jury_votes_count': jury_votes_count,
        'projets_count': projets_count,
        'total_votes': total_votes,
        'title': 'Fermer la session',
    })


@role_required('ADMIN', 'JURY', 'PRESIDENT_JURY', 'STUDENT')
def session_results_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    resultats = session.resultats.select_related('projet', 'projet__student').all()

    if request.user.role == 'STUDENT' and session.status != SessionVote.Status.PUBLISHED:
        messages.error(request, 'Les résultats ne sont pas encore publiés.')
        return redirect('home')

    if request.user.role == 'JURY' and request.user not in session.jury.all() and session.status != SessionVote.Status.PUBLISHED:
        messages.error(request, 'Accès refusé.')
        return redirect('home')

    if request.user.role == 'STUDENT':
        mon_resultat = resultats.filter(projet__student=request.user).first()
    else:
        mon_resultat = None

    votes_details = None
    if request.user.role in ('ADMIN', 'PRESIDENT_JURY', 'JURY'):
        votes_details = Vote.objects.filter(session=session).select_related(
            'jury', 'projet'
        ).prefetch_related('notes__critere')

    return render(request, 'session_results.html', {
        'session': session,
        'resultats': resultats,
        'mon_resultat': mon_resultat,
        'votes_details': votes_details,
        'title': f'Résultats — {session.nom}',
    })


@role_required('PRESIDENT_JURY', 'ADMIN')
def session_publish_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    if request.user.role != 'ADMIN' and request.user not in session.jury.all():
        return HttpResponseForbidden()

    if session.status != SessionVote.Status.CLOSED:
        messages.error(request, 'Seules les sessions fermées peuvent être publiées.')
        return redirect('session_results', pk=session.pk)

    if request.method == 'POST':
        session.status = SessionVote.Status.PUBLISHED
        session.published_at = timezone.now()
        session.published_by = request.user
        session.save(update_fields=['status', 'published_at', 'published_by'])
        log_action(request.user, ActionLog.Action.PUBLISH, model_name='SessionVote',
                   object_id=session.pk, details=f'Résultats publiés: {session.nom}')
        all_users = CustomUser.objects.filter(
            role__in=[CustomUser.Role.STUDENT, CustomUser.Role.JURY, CustomUser.Role.PRESIDENT_JURY]
        )
        for user in all_users:
            create_notification(
                user, Notification.Type.RESULTS_PUBLISHED,
                f'Les résultats de "{session.nom}" sont disponibles.',
                lien=reverse('session_results', args=[session.pk]),
            )
        messages.success(request, f'Résultats de "{session.nom}" publiés avec succès !')
        return redirect('session_results', pk=session.pk)

    resultats = session.resultats.select_related('projet', 'projet__student').all()
    return render(request, 'session_publish_confirm.html', {
        'session': session,
        'resultats': resultats,
        'title': 'Publier les résultats',
    })


@role_required('ADMIN', 'JURY', 'PRESIDENT_JURY', 'STUDENT')
def results_public_view(request):
    sessions = SessionVote.objects.filter(status=SessionVote.Status.PUBLISHED)
    selected_pk = request.GET.get('session')
    resultats = None
    selected_session = None

    if selected_pk:
        selected_session = get_object_or_404(SessionVote, pk=selected_pk, status=SessionVote.Status.PUBLISHED)
        resultats = Resultat.objects.filter(session=selected_session).select_related(
            'projet', 'projet__student'
        ).order_by('rang')

    return render(request, 'results_public.html', {
        'sessions': sessions,
        'selected_session': selected_session,
        'resultats': resultats,
        'title': 'Résultats publics',
    })


@role_required('PRESIDENT_JURY', 'ADMIN')
def report_pdf_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    if request.user.role != 'ADMIN' and request.user not in session.jury.all():
        return HttpResponseForbidden()

    resultats = session.resultats.select_related('projet', 'projet__student').order_by('rang')
    votes_details = Vote.objects.filter(session=session).select_related(
        'jury', 'projet'
    ).prefetch_related('notes__critere')

    html = render_to_string('report_pdf.html', {
        'session': session,
        'resultats': resultats,
        'votes_details': votes_details,
        'generated_by': request.user.get_full_name() or request.user.email,
        'generated_at': timezone.now(),
    })

    from weasyprint import HTML
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="rapport_{session.nom}_{timezone.now().date()}.pdf"'
    HTML(string=html).write_pdf(response)

    if request.user.is_authenticated:
        from django.core.files.base import ContentFile
        rapport = Rapport.objects.create(
            session=session,
            format=Rapport.Format.PDF,
            genere_par=request.user,
        )
        pdf_content = HTML(string=html).write_pdf()
        rapport.fichier.save(
            f'rapport_{session.pk}_{timezone.now().date()}.pdf',
            ContentFile(pdf_content)
        )

    return response


@role_required('PRESIDENT_JURY', 'ADMIN')
def report_csv_view(request, pk):
    session = get_object_or_404(SessionVote, pk=pk)
    if request.user.role != 'ADMIN' and request.user not in session.jury.all():
        return HttpResponseForbidden()

    resultats = session.resultats.select_related('projet', 'projet__student').order_by('rang')
    votes_details = Vote.objects.filter(session=session).select_related(
        'jury', 'projet'
    ).prefetch_related('notes__critere')

    import io
    buffer = io.StringIO()
    buffer.write('\ufeff')
    writer = csv.writer(buffer)
    writer.writerow(['Rang', 'Projet', 'Étudiant', 'Score Final'])

    for c in session.criteres.all():
        writer.writerow([f'Note {c.nom} (/{c.note_max})'])

    writer.writerow([])

    for r in resultats:
        row = [r.rang, r.projet.title, r.projet.student.get_full_name() or r.projet.student.email, r.score_final]
        writer.writerow(row)

    writer.writerow([])
    writer.writerow(['Détail des votes par jury'])
    header = ['Projet', 'Jury'] + [c.nom for c in session.criteres.all()] + ['Total']
    writer.writerow(header)
    for vote in votes_details:
        notes_dict = {n.critere_id: n.note for n in vote.notes.all()}
        row = [vote.projet.title, vote.jury.get_full_name() or vote.jury.email]
        for c in session.criteres.all():
            row.append(notes_dict.get(c.pk, ''))
        row.append(vote.score_total)
        writer.writerow(row)

    content = buffer.getvalue()
    buffer.close()

    if request.user.is_authenticated:
        from django.core.files.base import ContentFile
        rapport = Rapport.objects.create(
            session=session,
            format=Rapport.Format.CSV,
            genere_par=request.user,
        )
        rapport.fichier.save(
            f'rapport_{session.pk}_{timezone.now().date()}.csv',
            ContentFile(content.encode('utf-8'))
        )

    response = HttpResponse(content.encode('utf-8'), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="resultats_{session.nom}_{timezone.now().date()}.csv"'
    return response


@role_required('ADMIN', 'JURY', 'PRESIDENT_JURY', 'STUDENT')
def notifications_view(request):
    notifications = Notification.objects.filter(user=request.user)
    Notification.objects.filter(user=request.user, lu=False).update(lu=True)
    return render(request, 'notifications.html', {
        'notifications': notifications,
        'title': 'Notifications',
    })
