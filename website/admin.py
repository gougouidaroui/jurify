from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, LoginHistory, Projet, SessionVote, Critere, Vote, Resultat, Rapport, Notification, ActionLog


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'username', 'role', 'is_active', 'failed_login_attempts', 'date_joined')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('Jurify', {'fields': ('role', 'failed_login_attempts', 'locked_until')}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Jurify', {'fields': ('role',)}),
    )


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip_address', 'logged_in_at')
    list_filter = ('logged_in_at',)
    search_fields = ('user__email', 'ip_address')
    ordering = ('-logged_in_at',)


@admin.register(Projet)
class ProjetAdmin(admin.ModelAdmin):
    list_display = ('title', 'filiere', 'status', 'student', 'created_at')
    list_filter = ('status', 'filiere')
    search_fields = ('title', 'student__email')


@admin.register(SessionVote)
class SessionVoteAdmin(admin.ModelAdmin):
    list_display = ('nom', 'filiere', 'status', 'date_debut', 'date_fin')
    list_filter = ('status', 'filiere')
    search_fields = ('nom',)
    filter_horizontal = ('projets', 'jury')


@admin.register(Critere)
class CritereAdmin(admin.ModelAdmin):
    list_display = ('nom', 'poids', 'note_max', 'session')
    list_filter = ('session',)


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('jury', 'projet', 'session', 'score_total', 'date_vote')
    list_filter = ('session',)


@admin.register(Resultat)
class ResultatAdmin(admin.ModelAdmin):
    list_display = ('projet', 'session', 'score_final', 'rang')
    list_filter = ('session',)
    ordering = ('session', 'rang')


@admin.register(Rapport)
class RapportAdmin(admin.ModelAdmin):
    list_display = ('session', 'format', 'genere_par', 'genere_le')
    list_filter = ('format', 'session')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'message', 'lu', 'created_at')
    list_filter = ('type', 'lu', 'created_at')


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'model_name', 'object_id', 'created_at')
    list_filter = ('action', 'created_at')
    date_hierarchy = 'created_at'
