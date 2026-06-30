from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("editor", "0004_layoutversion"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION editor_layoutversion_immutable()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'LayoutVersion is immutable once created';
            END;
            $$;

            CREATE TRIGGER editor_layoutversion_immutable
                BEFORE UPDATE ON editor_layoutversion
                FOR EACH ROW
                EXECUTE FUNCTION editor_layoutversion_immutable();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS editor_layoutversion_immutable
                ON editor_layoutversion;
            DROP FUNCTION IF EXISTS editor_layoutversion_immutable();
            """,
        ),
    ]
