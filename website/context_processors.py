from .models import Notification


def notifications_processor(request):
    if request.user.is_authenticated:
        return {
            'unread_notifications_count': Notification.objects.filter(
                user=request.user, lu=False
            ).count(),
        }
    return {}
