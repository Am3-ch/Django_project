from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.urls import reverse

class Post(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
    date_posted = models.DateTimeField(default=timezone.now)
    author = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('post-detail', kwargs={'pk': self.pk})

    @property
    def is_active(self):
        """A post counts as active for 24 hours after it was posted."""
        return timezone.now() - self.date_posted < timedelta(hours=24)

    @property
    def age_label(self):
        """Short age such as 'just now', '5m', '2h', '3d', '4w', '6mo', '1y'."""
        seconds = int((timezone.now() - self.date_posted).total_seconds())
        if seconds < 60:
            return 'just now'
        for unit, size in (('y', 31536000), ('mo', 2592000), ('w', 604800),
                           ('d', 86400), ('h', 3600), ('m', 60)):
            if seconds >= size:
                return f'{seconds // size}{unit} ago'
    