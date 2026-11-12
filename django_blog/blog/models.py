from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.urls import reverse


def short_age(moment):
    """Short age such as 'just now', '5m ago', '2h ago', '3d ago', '1y ago'."""
    seconds = int((timezone.now() - moment).total_seconds())
    if seconds < 60:
        return 'just now'
    for unit, size in (('y', 31536000), ('mo', 2592000), ('w', 604800),
                       ('d', 86400), ('h', 3600), ('m', 60)):
        if seconds >= size:
            return f'{seconds // size}{unit} ago'


class Post(models.Model):
    SEEKING = 'seeking'
    OFFERING = 'offering'
    KIND_CHOICES = [
        (SEEKING, "I'm looking for a mentor"),
        (OFFERING, "I'm offering to mentor"),
    ]

    title = models.CharField(max_length=100)
    content = models.TextField()
    date_posted = models.DateTimeField(default=timezone.now)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    kind = models.CharField('This post is', max_length=10, choices=KIND_CHOICES, default=SEEKING)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('post-detail', kwargs={'pk': self.pk})

    # ── Roles ──
    @property
    def kind_label(self):
        """Tag shown on the post (the choice labels are worded for the author's form)."""
        return 'Looking for a mentor' if self.kind == self.SEEKING else 'Offering mentorship'

    @property
    def author_role(self):
        return 'mentee' if self.kind == self.SEEKING else 'mentor'

    @property
    def member_role(self):
        """Role of everyone who joins the post's chat."""
        return 'mentor' if self.kind == self.SEEKING else 'mentee'

    def role_of(self, user):
        return self.author_role if user == self.author else self.member_role

    def can_chat(self, user):
        if not user.is_authenticated:
            return False
        return user == self.author or self.memberships.filter(user=user).exists()

    # ── Activity ──
    @property
    def last_activity(self):
        if hasattr(self, 'last_message_at'):  # annotated by the feed query
            last = self.last_message_at
        else:
            last = self.messages.order_by('-created_at').values_list('created_at', flat=True).first()
        return max(last, self.date_posted) if last else self.date_posted

    @property
    def is_active(self):
        """A post counts as active for 24 hours after it was posted or last messaged."""
        return timezone.now() - self.last_activity < timedelta(hours=24)

    @property
    def age_label(self):
        return short_age(self.last_activity)

    @property
    def is_live(self):
        """The chat had a message in the last 10 minutes."""
        return self.messages.filter(created_at__gte=timezone.now() - timedelta(minutes=10)).exists()


class Membership(models.Model):
    """A user who joined a post's mentorship group chat (the author is implicitly a member)."""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['post', 'user'], name='unique_post_member'),
        ]
        ordering = ['joined_at']

    def __str__(self):
        return f'{self.user} in {self.post}'


class Message(models.Model):
    MAX_LENGTH = 2000

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    body = models.TextField(max_length=MAX_LENGTH)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.sender}: {self.body[:40]}'
