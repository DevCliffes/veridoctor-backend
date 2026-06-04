from django.db import models
import uuid


class BaseModel(models.Model):
    """
    Instance of a django Model tha contains uuid primary key and time stamps for all other models
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
