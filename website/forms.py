from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm
from django.contrib.auth import authenticate
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from .models import CustomUser, Projet, SessionVote, Critere, Vote, NoteParCritere


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'Adresse e-mail', 'class': 'w-full px-4 py-2 border rounded-lg'})
    )
    username = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'placeholder': "Nom d'utilisateur", 'class': 'w-full px-4 py-2 border rounded-lg'})
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Prénom', 'class': 'w-full px-4 py-2 border rounded-lg'})
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Nom', 'class': 'w-full px-4 py-2 border rounded-lg'})
    )

    class Meta:
        model = CustomUser
        fields = ('email', 'username', 'first_name', 'last_name', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'placeholder': 'Mot de passe',
            'class': 'w-full px-4 py-2 border rounded-lg'
        })
        self.fields['password2'].widget.attrs.update({
            'placeholder': 'Confirmer le mot de passe',
            'class': 'w-full px-4 py-2 border rounded-lg'
        })
        self.fields['password1'].help_text = None
        self.fields['password2'].help_text = None

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = CustomUser.Role.STUDENT
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'Adresse e-mail', 'class': 'w-full px-4 py-2 border rounded-lg'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Mot de passe', 'class': 'w-full px-4 py-2 border rounded-lg'})
    )

    error_messages = {
        'invalid_login': "Email ou mot de passe incorrect.",
        'inactive': "Ce compte est désactivé.",
        'locked': "Ce compte est temporairement verrouillé après trop de tentatives échouées. Réessayez plus tard.",
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')

        if email and password:
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )

            if not user.is_active:
                raise forms.ValidationError(
                    self.error_messages['inactive'],
                    code='inactive',
                )

            if user.locked_until and timezone.now() < user.locked_until:
                remaining = (user.locked_until - timezone.now()).seconds // 60
                raise forms.ValidationError(
                    f"Compte verrouillé. Réessayez dans {remaining} minute(s).",
                    code='locked',
                )

            self.user_cache = authenticate(self.request, username=email, password=password)

            if self.user_cache is None:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
                    user.locked_until = timezone.now() + timezone.timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
                user.save(update_fields=['failed_login_attempts', 'locked_until'])
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )

            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=['failed_login_attempts', 'locked_until'])

        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'w-full px-4 py-2 border rounded-lg'


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'username')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'username': forms.TextInput(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
        }


class ProjectForm(forms.ModelForm):
    team_members = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.filter(role=CustomUser.Role.STUDENT),
        widget=forms.SelectMultiple(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg select2-search',
            'data-placeholder': 'Rechercher des étudiants...',
        }),
        label='Membres de l\'équipe',
        required=False,
    )

    class Meta:
        model = Projet
        fields = ('title', 'description', 'filiere', 'team_members', 'document')
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'placeholder': 'Titre du projet'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'rows': 5,
                'placeholder': 'Description du projet'
            }),
            'filiere': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg'
            }),
            'document': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg'
            }),
        }
        labels = {
            'title': 'Titre du projet',
            'description': 'Description',
            'filiere': 'Filière',
            'document': 'Document du projet',
        }

    def clean_team_members(self):
        users = self.cleaned_data.get('team_members') or []
        if len(users) > 4:
            raise forms.ValidationError('Maximum 4 membres supplémentaires autorisés.')
        # Exclude the project owner
        owner_email = getattr(self.instance, '_owner_email', None)
        if owner_email:
            users = [u for u in users if u.email != owner_email]
        return [u.email for u in users]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.team_members:
            stored_emails = self.instance.team_members
            matched = CustomUser.objects.filter(email__in=stored_emails)
            self.initial['team_members'] = matched
        elif not self.initial.get('team_members'):
            self.initial['team_members'] = CustomUser.objects.none()


class SessionForm(forms.ModelForm):
    class Meta:
        model = SessionVote
        fields = ('nom', 'date_debut', 'date_fin', 'filiere', 'projets', 'jury')
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'placeholder': 'Ex: Session PFA 2025'
            }),
            'date_debut': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'type': 'datetime-local',
            }),
            'date_fin': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'type': 'datetime-local',
            }),
            'filiere': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'projets': forms.SelectMultiple(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'size': 8,
            }),
            'jury': forms.SelectMultiple(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'size': 8,
            }),
        }
        labels = {
            'nom': 'Nom de la session',
            'date_debut': 'Date de début',
            'date_fin': 'Date de fin',
            'filiere': 'Filière',
            'projets': 'Projets à évaluer',
            'jury': 'Membres du jury',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['projets'].queryset = Projet.objects.filter(status=Projet.Status.VALIDATED)
        self.fields['jury'].queryset = CustomUser.objects.filter(
            role__in=[CustomUser.Role.JURY, CustomUser.Role.PRESIDENT_JURY]
        )

    def clean(self):
        cleaned_data = super().clean()
        date_debut = cleaned_data.get('date_debut')
        date_fin = cleaned_data.get('date_fin')
        if date_debut and date_fin and date_debut >= date_fin:
            raise ValidationError('La date de fin doit être après la date de début.')
        return cleaned_data


class CritereForm(forms.ModelForm):
    class Meta:
        model = Critere
        fields = ('nom', 'poids', 'note_max')
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'placeholder': 'Ex: Qualité du code'
            }),
            'poids': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'step': '0.01',
                'placeholder': 'Ex: 25'
            }),
            'note_max': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'step': '0.5',
                'placeholder': 'Ex: 20'
            }),
        }
        labels = {
            'nom': 'Nom du critère',
            'poids': 'Poids (%)',
            'note_max': 'Note maximale',
        }


class CritereFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        total_poids = 0
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                total_poids += float(form.cleaned_data.get('poids', 0))
        if total_poids != 100.0:
            raise ValidationError(
                f'La somme des poids doit être égale à 100% (actuellement: {total_poids}%).'
            )


class JuryAssignForm(forms.ModelForm):
    class Meta:
        model = SessionVote
        fields = ('jury',)
        widgets = {
            'jury': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['jury'].queryset = CustomUser.objects.filter(
            role__in=[CustomUser.Role.JURY, CustomUser.Role.PRESIDENT_JURY]
        )
        self.fields['jury'].label_from_instance = lambda obj: f"{obj.get_full_name() or obj.email} ({obj.get_role_display()})"


class ProjectAssignForm(forms.ModelForm):
    class Meta:
        model = SessionVote
        fields = ('projets',)
        widgets = {
            'projets': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['projets'].queryset = Projet.objects.filter(
            status=Projet.Status.VALIDATED
        )
        self.fields['projets'].label_from_instance = lambda obj: f"{obj.title} — {obj.student.get_full_name() or obj.student.email}"


class SessionOpenForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label='Je confirme l\'ouverture de cette session de vote',
    )


class ProjectAdminForm(forms.ModelForm):
    class Meta:
        model = Projet
        fields = ('status', 'rejection_reason')
        widgets = {
            'status': forms.Select(attrs={'class': 'w-full px-4 py-2 border rounded-lg'}),
            'rejection_reason': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border rounded-lg',
                'rows': 3,
                'placeholder': 'Motif du rejet (obligatoire si rejeté)'
            }),
        }


class VoteForm(forms.Form):
    commentaire = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2 border rounded-lg',
            'rows': 3,
            'placeholder': 'Commentaire facultatif sur ce projet...'
        }),
        label='Commentaire',
    )

    def __init__(self, *args, session=None, projet=None, existing_vote=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.projet = projet
        self.existing_vote = existing_vote

        if session:
            for critere in session.criteres.all():
                initial_value = None
                if existing_vote:
                    try:
                        note = existing_vote.notes.get(critere=critere)
                        initial_value = note.note
                    except NoteParCritere.DoesNotExist:
                        pass

                self.fields[f'note_{critere.pk}'] = forms.DecimalField(
                    required=True,
                    min_value=0,
                    max_value=float(critere.note_max),
                    initial=initial_value,
                    widget=forms.NumberInput(attrs={
                        'class': 'w-full px-4 py-2 border rounded-lg',
                        'step': '0.5',
                        'placeholder': f'0 - {float(critere.note_max):g}',
                    }),
                    label=critere.nom,
                    help_text=f'sur {float(critere.note_max):g} (poids: {float(critere.poids):g}%)',
                )

    def save(self, jury, ip_address):
        from django.db.models import Sum

        if self.existing_vote:
            vote = self.existing_vote
            vote.commentaire = self.cleaned_data['commentaire']
            vote.ip_address = ip_address
            vote.save(update_fields=['commentaire', 'ip_address', 'modified_at'])
            vote.notes.all().delete()
        else:
            vote = Vote.objects.create(
                jury=jury,
                projet=self.projet,
                session=self.session,
                commentaire=self.cleaned_data['commentaire'],
                ip_address=ip_address,
                score_total=0,
            )

        for critere in self.session.criteres.all():
            note_val = self.cleaned_data[f'note_{critere.pk}']
            NoteParCritere.objects.create(
                vote=vote,
                critere=critere,
                note=note_val,
            )

        vote.recalculer_score()
        return vote
