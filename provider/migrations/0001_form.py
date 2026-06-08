from django.db import migrations


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'provider_form'
                ) THEN
                    CREATE TABLE provider_form (
                        id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
                        name varchar(200) NOT NULL,
                        sections jsonb NOT NULL DEFAULT '[]'::jsonb,
                        created_at timestamptz NOT NULL DEFAULT now(),
                        updated_at timestamptz NOT NULL DEFAULT now(),
                        provider_id uuid NOT NULL REFERENCES provider_healthcareprovider(id) ON DELETE CASCADE
                    );
                END IF;
            END $$;
            """,
            reverse_sql="DROP TABLE IF EXISTS provider_form;"
        ),
    ]
