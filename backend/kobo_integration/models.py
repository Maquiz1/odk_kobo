from django.db import models

class Record(models.Model):
    """
    Represents a submission from KoboToolbox.
    Records are scoped to a Project; users only see records for their projects.
    """
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='records',
        help_text='The project this submission belongs to.'
    )
    kobo_id = models.CharField(max_length=255, unique=True)
    uuid = models.CharField(max_length=255, blank=True, null=True)
    submitted_by = models.CharField(max_length=255, blank=True, null=True)
    
    # We store the raw form data in a JSON field for flexibility
    data = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Record {self.kobo_id} [{self.project}]"
