from django.db import models
from django.contrib.auth.models import User


class AdminLog(models.Model):
    """Tracks admin panel actions (create/edit/delete/import/login)."""
    ACTION_CHOICES = [
        ('create', 'Create'), ('update', 'Update'), ('delete', 'Delete'),
        ('import', 'Import'), ('export', 'Export'), ('login',  'Login'),
        ('wipe',   'Wipe'),
    ]
    user       = models.ForeignKey(User, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='admin_logs')
    action     = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100, blank=True)
    object_id  = models.CharField(max_length=50,  blank=True)
    details    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_log'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} — {self.action} {self.model_name} @ {self.created_at:%Y-%m-%d %H:%M}"