from django.db import models


class UserMetric(models.Model):
    user_id = models.IntegerField()
    event = models.CharField(max_length=64)
    ts = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"UserMetric(user={self.user_id}, event={self.event}, ts={self.ts})"
