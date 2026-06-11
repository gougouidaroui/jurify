from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrateur'
        JURY = 'JURY', 'Membre du Jury'
        PRESIDENT_JURY = 'PRESIDENT_JURY', 'Président du Jury'
        STUDENT = 'STUDENT', 'Étudiant'
        GUEST = 'GUEST', 'Invité'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    email = models.EmailField(unique=True)
    failed_login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    def __str__(self):
        return f"{self.get_full_name() or self.email} ({self.get_role_display()})"


class LoginHistory(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='login_history')
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    logged_in_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Historique de connexion'
        verbose_name_plural = 'Historiques de connexions'
        ordering = ['-logged_in_at']

    def __str__(self):
        return f"{self.user.email} - {self.logged_in_at}"


class Projet(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Brouillon'
        SUBMITTED = 'SUBMITTED', 'Soumis'
        VALIDATED = 'VALIDATED', 'Validé'
        REJECTED = 'REJECTED', 'Rejeté'

    class Filiere(models.TextChoices):
        IR = 'IR', 'Ingénierie Informatique'
        IIR = 'IIR', 'Ingénierie Informatique et Réseaux'
        GSE = 'GSE', 'Génie des Systèmes Embarqués'
        BI = 'BI', 'Business Intelligence'

    title = models.CharField('Titre', max_length=200)
    description = models.TextField('Description')
    filiere = models.CharField('Filière', max_length=5, choices=Filiere.choices)
    status = models.CharField('Statut', max_length=20, choices=Status.choices, default=Status.DRAFT)
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='projets', verbose_name='Étudiant')
    team_members = models.JSONField('Membres de l\'équipe', default=list, blank=True)
    document = models.FileField('Document', upload_to='projets/', blank=True, null=True)
    created_at = models.DateTimeField('Créé le', auto_now_add=True)
    updated_at = models.DateTimeField('Mis à jour le', auto_now=True)
    submitted_at = models.DateTimeField('Soumis le', null=True, blank=True)
    validated_at = models.DateTimeField('Validé le', null=True, blank=True)
    validated_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='validations', verbose_name='Validé par'
    )
    rejection_reason = models.TextField('Motif du rejet', blank=True)

    class Meta:
        verbose_name = 'Projet'
        verbose_name_plural = 'Projets'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.title = self.title.strip()
        super().save(*args, **kwargs)

    def can_edit(self, user):
        return self.student == user and self.status in (self.Status.DRAFT, self.Status.SUBMITTED)


class SessionVote(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planifiée'
        OPEN = 'OPEN', 'Ouverte'
        CLOSED = 'CLOSED', 'Fermée'
        PUBLISHED = 'PUBLISHED', 'Publiée'

    nom = models.CharField('Nom', max_length=200)
    date_debut = models.DateTimeField('Date de début')
    date_fin = models.DateTimeField('Date de fin')
    filiere = models.CharField('Filière', max_length=5, choices=Projet.Filiere.choices)
    status = models.CharField('Statut', max_length=20, choices=Status.choices, default=Status.PLANNED)
    created_by = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='sessions_created',
        verbose_name='Créée par'
    )
    projets = models.ManyToManyField(
        Projet, related_name='sessions', blank=True, verbose_name='Projets'
    )
    jury = models.ManyToManyField(
        CustomUser, related_name='sessions_jury', blank=True, verbose_name='Membres du jury'
    )
    created_at = models.DateTimeField('Créée le', auto_now_add=True)
    updated_at = models.DateTimeField('Modifiée le', auto_now=True)
    closed_at = models.DateTimeField('Fermée le', null=True, blank=True)
    published_at = models.DateTimeField('Publiée le', null=True, blank=True)
    closed_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions_closed', verbose_name='Fermée par'
    )
    published_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions_published', verbose_name='Publiée par'
    )

    class Meta:
        verbose_name = 'Session de vote'
        verbose_name_plural = 'Sessions de vote'
        ordering = ['-date_debut']

    def __str__(self):
        return self.nom

    def poids_total(self):
        from django.db.models import Sum
        return self.criteres.aggregate(total=Sum('poids'))['total'] or 0

    def all_jury_voted(self):
        jury_ids = set(self.jury.values_list('pk', flat=True))
        voted_jury_ids = set(self.votes.values_list('jury_id', flat=True).distinct())
        return jury_ids == voted_jury_ids, jury_ids - voted_jury_ids

    def calculer_resultats(self):
        from django.db.models import Avg
        self.resultats.all().delete()
        results = []
        for projet in self.projets.all():
            avg = self.votes.filter(projet=projet).aggregate(avg_score=Avg('score_total'))
            score = avg['avg_score'] or 0
            results.append((projet, round(score, 2)))
        results.sort(key=lambda x: x[1], reverse=True)
        for rang, (projet, score) in enumerate(results, start=1):
            Resultat.objects.create(
                projet=projet,
                session=self,
                score_final=score,
                rang=rang,
            )
        return results


class Critere(models.Model):
    nom = models.CharField('Nom', max_length=100)
    poids = models.DecimalField('Poids (%)', max_digits=5, decimal_places=2,
                                help_text='Poids en pourcentage')
    note_max = models.DecimalField('Note maximale', max_digits=5, decimal_places=2, default=20)
    session = models.ForeignKey(
        SessionVote, on_delete=models.CASCADE, related_name='criteres',
        verbose_name='Session'
    )

    class Meta:
        verbose_name = 'Critère'
        verbose_name_plural = 'Critères'
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.poids}%)"


class Vote(models.Model):
    jury = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='votes',
        verbose_name='Jury'
    )
    projet = models.ForeignKey(
        Projet, on_delete=models.CASCADE, related_name='votes',
        verbose_name='Projet'
    )
    session = models.ForeignKey(
        SessionVote, on_delete=models.CASCADE, related_name='votes',
        verbose_name='Session'
    )
    score_total = models.DecimalField('Score total', max_digits=7, decimal_places=2, default=0)
    commentaire = models.TextField('Commentaire', blank=True)
    ip_address = models.GenericIPAddressField('Adresse IP')
    date_vote = models.DateTimeField('Date du vote', auto_now_add=True)
    modified_at = models.DateTimeField('Modifié le', auto_now=True)

    class Meta:
        verbose_name = 'Vote'
        verbose_name_plural = 'Votes'
        constraints = [
            models.UniqueConstraint(
                fields=['jury', 'projet', 'session'],
                name='unique_vote_per_jury_project_session'
            )
        ]

    def __str__(self):
        return f"{self.jury.email} → {self.projet.title} ({self.score_total})"

    def recalculer_score(self):
        total = 0
        for note in self.notes.all():
            poids = note.critere.poids
            note_max = note.critere.note_max
            score = float(note.note) * float(poids) / 100.0
            total += score
        self.score_total = round(total, 2)
        self.save(update_fields=['score_total'])
        return self.score_total


class NoteParCritere(models.Model):
    vote = models.ForeignKey(
        Vote, on_delete=models.CASCADE, related_name='notes',
        verbose_name='Vote'
    )
    critere = models.ForeignKey(
        Critere, on_delete=models.CASCADE, related_name='notes',
        verbose_name='Critère'
    )
    note = models.DecimalField('Note', max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = 'Note par critère'
        verbose_name_plural = 'Notes par critère'
        constraints = [
            models.UniqueConstraint(
                fields=['vote', 'critere'],
                name='unique_note_per_vote_critere'
            )
        ]

    def __str__(self):
        return f"{self.critere.nom}: {self.note}/{self.critere.note_max}"


class Resultat(models.Model):
    projet = models.ForeignKey(
        Projet, on_delete=models.CASCADE, related_name='resultats',
        verbose_name='Projet'
    )
    session = models.ForeignKey(
        SessionVote, on_delete=models.CASCADE, related_name='resultats',
        verbose_name='Session'
    )
    score_final = models.DecimalField('Score final', max_digits=7, decimal_places=2)
    rang = models.IntegerField('Rang')
    created_at = models.DateTimeField('Créé le', auto_now_add=True)

    class Meta:
        verbose_name = 'Résultat'
        verbose_name_plural = 'Résultats'
        ordering = ['rang']

    def __str__(self):
        return f"{self.projet.title} — Rang {self.rang} ({self.score_final})"


class Rapport(models.Model):
    class Format(models.TextChoices):
        PDF = 'PDF', 'PDF'
        CSV = 'CSV', 'CSV'

    session = models.ForeignKey(
        SessionVote, on_delete=models.CASCADE, related_name='rapports',
        verbose_name='Session'
    )
    format = models.CharField('Format', max_length=5, choices=Format.choices)
    genere_par = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rapports_generes', verbose_name='Généré par'
    )
    fichier = models.FileField('Fichier', upload_to='rapports/', blank=True, null=True)
    genere_le = models.DateTimeField('Généré le', auto_now_add=True)

    class Meta:
        verbose_name = 'Rapport'
        verbose_name_plural = 'Rapports'
        ordering = ['-genere_le']

    def __str__(self):
        return f"Rapport {self.format} — {self.session.nom} ({self.genere_le.date()})"


class Notification(models.Model):
    class Type(models.TextChoices):
        INFO = 'INFO', 'Information'
        VOTE_OPEN = 'VOTE_OPEN', 'Session ouverte'
        VOTE_CLOSED = 'VOTE_CLOSED', 'Session fermée'
        RESULTS_PUBLISHED = 'RESULTS_PUBLISHED', 'Résultats publiés'
        PROJECT_VALIDATED = 'PROJECT_VALIDATED', 'Projet validé'
        PROJECT_REJECTED = 'PROJECT_REJECTED', 'Projet rejeté'

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='notifications',
        verbose_name='Utilisateur'
    )
    type = models.CharField('Type', max_length=30, choices=Type.choices, default=Type.INFO)
    message = models.CharField('Message', max_length=255)
    lien = models.CharField('Lien', max_length=200, blank=True, help_text='URL optionnelle')
    lu = models.BooleanField('Lue', default=False)
    created_at = models.DateTimeField('Créée le', auto_now_add=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']

    def __str__(self):
        return self.message[:60]


class ActionLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = 'LOGIN', 'Connexion'
        LOGOUT = 'LOGOUT', 'Déconnexion'
        CREATE = 'CREATE', 'Création'
        UPDATE = 'UPDATE', 'Modification'
        DELETE = 'DELETE', 'Suppression'
        VOTE = 'VOTE', 'Vote'
        CLOSE = 'CLOSE', 'Fermeture'
        PUBLISH = 'PUBLISH', 'Publication'
        VALIDATE = 'VALIDATE', 'Validation'

    user = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='actions', verbose_name='Utilisateur'
    )
    action = models.CharField('Action', max_length=20, choices=Action.choices)
    model_name = models.CharField('Modèle', max_length=50, blank=True)
    object_id = models.IntegerField('ID Objet', null=True, blank=True)
    details = models.TextField('Détails', blank=True)
    ip_address = models.GenericIPAddressField('Adresse IP', blank=True, null=True)
    created_at = models.DateTimeField('Date', auto_now_add=True)

    class Meta:
        verbose_name = 'Journal d\'action'
        verbose_name_plural = 'Journaux d\'actions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_display()} — {self.user} ({self.created_at})"


def create_notification(user, type, message, lien=''):
    Notification.objects.create(
        user=user,
        type=type,
        message=message,
        lien=lien,
    )


def log_action(user, action, model_name='', object_id=None, details='', ip_address=''):
    ActionLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        details=details,
        ip_address=ip_address or '',
    )


@receiver(post_delete, sender=Projet)
def delete_projet_file_on_delete(sender, instance, **kwargs):
    if instance.document:
        instance.document.delete(False)


@receiver(pre_save, sender=Projet)
def delete_projet_file_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old = Projet.objects.get(pk=instance.pk)
    except Projet.DoesNotExist:
        return
    if old.document and old.document.name != instance.document.name:
        old.document.delete(False)
