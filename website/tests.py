from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import (
    Projet, SessionVote, Critere, Vote, NoteParCritere, Resultat,
    Notification, ActionLog
)

CustomUser = get_user_model()


class BaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create_user(
            username='admin', email='admin@test.com', password='admin123',
            role=CustomUser.Role.ADMIN, is_staff=True, is_superuser=True,
        )
        cls.jury1 = CustomUser.objects.create_user(
            username='jury1', email='jury1@test.com', password='test123',
            role=CustomUser.Role.JURY,
        )
        cls.jury2 = CustomUser.objects.create_user(
            username='jury2', email='jury2@test.com', password='test123',
            role=CustomUser.Role.JURY,
        )
        cls.president = CustomUser.objects.create_user(
            username='president', email='president@test.com', password='test123',
            role=CustomUser.Role.PRESIDENT_JURY,
        )
        cls.student = CustomUser.objects.create_user(
            username='student', email='student@test.com', password='test123',
            role=CustomUser.Role.STUDENT,
        )
        cls.client = Client()

    def login(self, user):
        self.client.login(email=user.email, password='test123' if user != self.admin else 'admin123')

    def create_project(self, title='Projet Test', student=None, status=Projet.Status.DRAFT):
        student = student or self.student
        return Projet.objects.create(
            title=title,
            description='Description test',
            filiere='GLSI',
            status=status,
            student=student,
        )

    def create_session(self, status=SessionVote.Status.PLANNED, created_by=None):
        session = SessionVote.objects.create(
            nom='Session Test',
            filiere='GLSI',
            date_debut=timezone.now().date(),
            date_fin=timezone.now().date() + timezone.timedelta(days=7),
            status=status,
            created_by=created_by or self.admin,
        )
        session.jury.add(self.jury1, self.jury2, self.president)
        return session

    def create_criteria(self, session, *weights):
        criteria = []
        for w in weights:
            c = Critere.objects.create(
                session=session, nom='Critere', poids=w, note_max=20
            )
            criteria.append(c)
        return criteria

    def assign_projects(self, session, *projects):
        session.projets.add(*projects)


class RG3AccountLockoutTest(BaseTestCase):
    def test_lockout_after_3_failed_attempts(self):
        for i in range(3):
            self.client.post(reverse('login'), {
                'email': self.admin.email, 'password': 'wrongpass'
            })
        self.admin.refresh_from_db()
        self.assertIsNotNone(self.admin.locked_until)
        self.assertGreater(self.admin.locked_until, timezone.now())
        self.assertEqual(self.admin.failed_login_attempts, 3)
        response = self.client.post(reverse('login'), {
            'email': self.admin.email, 'password': 'admin123'
        })
        self.assertContains(response, 'verrouillé')

    def test_lockout_reset_on_successful_login(self):
        for i in range(2):
            self.client.post(reverse('login'), {
                'email': self.admin.email, 'password': 'wrongpass'
            })
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.failed_login_attempts, 2)
        response = self.client.post(reverse('login'), {
            'email': self.admin.email, 'password': 'admin123'
        })
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.failed_login_attempts, 0)
        self.assertIsNone(self.admin.locked_until)


class RG5WeightSumTest(BaseTestCase):
    def test_weight_sum_validation_on_session_open(self):
        self.login(self.admin)
        session = self.create_session()
        self.create_criteria(session, 50, 30)
        projet = self.create_project(status=Projet.Status.VALIDATED)
        self.assign_projects(session, projet)
        response = self.client.post(reverse('session_open', args=[session.pk]), {'confirm': True})
        session.refresh_from_db()
        self.assertEqual(session.status, SessionVote.Status.PLANNED)
        self.assertEqual(response.status_code, 302)

    def test_weight_sum_valid_on_session_open(self):
        self.login(self.admin)
        session = self.create_session()
        self.create_criteria(session, 50, 30, 20)
        projet = self.create_project(status=Projet.Status.VALIDATED)
        self.assign_projects(session, projet)
        response = self.client.post(reverse('session_open', args=[session.pk]), {'confirm': True})
        session.refresh_from_db()
        self.assertEqual(session.status, SessionVote.Status.OPEN)


class RG6UniqueVoteTest(BaseTestCase):
    def test_unique_vote_per_jury_project_session(self):
        self.login(self.admin)
        session = self.create_session(SessionVote.Status.OPEN)
        self.create_criteria(session, 100)
        projet = self.create_project(status=Projet.Status.VALIDATED)
        self.assign_projects(session, projet)
        self.client.login(email=self.jury1.email, password='test123')
        Vote.objects.create(
            jury=self.jury1, projet=projet, session=session,
            score_total=Decimal('15.00'), ip_address='127.0.0.1',
        )
        with self.assertRaises(Exception):
            Vote.objects.create(
                jury=self.jury1, projet=projet, session=session,
                score_total=Decimal('18.00'), ip_address='127.0.0.1',
            )


class RG7VoteOnlyWhenOpenTest(BaseTestCase):
    def test_vote_modification_only_when_open(self):
        session = self.create_session(SessionVote.Status.PLANNED)
        self.create_criteria(session, 100)
        projet = self.create_project(status=Projet.Status.VALIDATED)
        self.assign_projects(session, projet)
        self.client.login(email=self.jury1.email, password='test123')
        response = self.client.get(reverse('vote_project', args=[session.pk, projet.pk]))
        self.assertNotEqual(response.status_code, 200)

    def test_vote_allowed_when_open(self):
        self.login(self.admin)
        session = self.create_session(SessionVote.Status.OPEN)
        criteria = self.create_criteria(session, 100)
        projet = self.create_project(status=Projet.Status.VALIDATED)
        self.assign_projects(session, projet)
        self.client.login(email=self.jury1.email, password='test123')
        data = {f'note_{criteria[0].pk}': '15'}
        response = self.client.post(reverse('vote_project', args=[session.pk, projet.pk]), data)
        # Should redirect after successful vote
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Vote.objects.filter(jury=self.jury1, projet=projet, session=session).exists())


class RG8ClosureOnlyWhenAllVotedTest(BaseTestCase):
    def test_closure_blocked_when_not_all_voted(self):
        self.login(self.admin)
        session = self.create_session(SessionVote.Status.OPEN)
        self.create_criteria(session, 100)
        projet = self.create_project(status=Projet.Status.VALIDATED)
        self.assign_projects(session, projet)
        # Only jury1 votes -> not all have voted
        Vote.objects.create(
            jury=self.jury1, projet=projet, session=session,
            score_total=Decimal('15.00'), ip_address='127.0.0.1',
        )
        response = self.client.post(reverse('session_close', args=[session.pk]), {'confirm': True})
        session.refresh_from_db()
        self.assertEqual(session.status, SessionVote.Status.OPEN)

    def test_closure_allowed_when_all_voted(self):
        self.login(self.admin)
        session = self.create_session(SessionVote.Status.OPEN)
        self.create_criteria(session, 100)
        projet = self.create_project(status=Projet.Status.VALIDATED)
        self.assign_projects(session, projet)
        for jury in [self.jury1, self.jury2, self.president]:
            Vote.objects.create(
                jury=jury, projet=projet, session=session,
                score_total=Decimal('15.00'), ip_address='127.0.0.1',
            )
        response = self.client.post(reverse('session_close', args=[session.pk]), {'confirm': True})
        session.refresh_from_db()
        self.assertEqual(session.status, SessionVote.Status.CLOSED)


class RG10ResultsVisibilityTest(BaseTestCase):
    def test_student_sees_only_own_result(self):
        session = self.create_session(SessionVote.Status.PUBLISHED)
        self.create_criteria(session, 100)
        projet1 = self.create_project(title='Mon Projet Test', status=Projet.Status.VALIDATED)
        autre_student = CustomUser.objects.create_user(
            username='student2', email='student2@test.com', password='test123',
            role=CustomUser.Role.STUDENT,
        )
        projet2 = self.create_project(
            title='Projet Autre', student=autre_student,
            status=Projet.Status.VALIDATED,
        )
        self.assign_projects(session, projet1, projet2)
        Resultat.objects.create(projet=projet1, session=session, score_final=Decimal('15.00'), rang=1)
        Resultat.objects.create(projet=projet2, session=session, score_final=Decimal('12.00'), rang=2)
        self.client.login(email=self.student.email, password='test123')
        response = self.client.get(reverse('session_results', args=[session.pk]))
        self.assertContains(response, 'Mon Projet Test')
        self.assertContains(response, 'Projet Autre')

    def test_results_not_visible_before_publication(self):
        session = self.create_session(SessionVote.Status.CLOSED)
        self.client.login(email=self.student.email, password='test123')
        response = self.client.get(reverse('session_results', args=[session.pk]))
        self.assertEqual(response.status_code, 302)

    def test_guest_sees_only_public_page(self):
        session = self.create_session(SessionVote.Status.PUBLISHED)
        self.create_criteria(session, 100)
        projet = self.create_project(status=Projet.Status.VALIDATED)
        self.assign_projects(session, projet)
        Resultat.objects.create(projet=projet, session=session, score_final=Decimal('15.00'), rang=1)
        response = self.client.get(reverse('results_public'), {'session': session.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, projet.title)


class NotificationTest(BaseTestCase):
    def test_create_notification(self):
        Notification.objects.create(
            user=self.jury1,
            type=Notification.Type.INFO,
            message='Test notification',
        )
        self.assertEqual(Notification.objects.filter(user=self.jury1).count (), 1)

    def test_notification_marked_read(self):
        notif = Notification.objects.create(
            user=self.jury1,
            type=Notification.Type.INFO,
            message='Test notification',
        )
        self.assertFalse(notif.lu)
        notif.lu = True
        notif.save()
        notif.refresh_from_db()
        self.assertTrue(notif.lu)


class ActionLogTest(BaseTestCase):
    def test_log_action_created(self):
        ActionLog.objects.create(
            user=self.admin,
            action=ActionLog.Action.CREATE,
            model_name='Projet',
            object_id=1,
            details='Test log',
        )
        self.assertEqual(ActionLog.objects.count(), 1)
