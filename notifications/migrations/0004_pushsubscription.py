from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0003_appointment_reminder_log"),
        ("identity", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="PushSubscription",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("endpoint", models.URLField(max_length=500)),
                        ("p256dh", models.CharField(max_length=255)),
                        ("auth", models.CharField(max_length=255)),
                        ("user_agent", models.CharField(blank=True, max_length=255)),
                        ("identity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_subscriptions", to="identity.identity")),
                    ],
                    options={},
                ),
                migrations.AddConstraint(
                    model_name="pushsubscription",
                    constraint=models.UniqueConstraint(fields=("identity", "endpoint"), name="unique_push_subscription_per_identity_endpoint"),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE TABLE IF NOT EXISTS notifications_pushsubscription (
                            id UUID PRIMARY KEY NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            endpoint VARCHAR(500) NOT NULL,
                            p256dh VARCHAR(255) NOT NULL,
                            auth VARCHAR(255) NOT NULL,
                            user_agent VARCHAR(255) NOT NULL DEFAULT '',
                            identity_id UUID NOT NULL REFERENCES identity_identity(id) ON DELETE CASCADE
                        );
                        CREATE UNIQUE INDEX IF NOT EXISTS unique_push_subscription_per_identity_endpoint
                            ON notifications_pushsubscription (identity_id, endpoint);
                    """,
                    reverse_sql="DROP TABLE IF EXISTS notifications_pushsubscription;",
                ),
            ],
        ),
    ]
