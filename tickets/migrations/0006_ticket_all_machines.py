from django.db import migrations, models


def restore_imported_all(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    Imported = apps.get_model("tickets", "SpreadsheetImport")
    alias = schema_editor.connection.alias
    ids = [record.ticket_id for record in Imported.objects.using(alias).all()
           if record.original_equipment.strip().casefold() == "todas"]
    Ticket.objects.using(alias).filter(pk__in=ids).update(all_machines=True)


class Migration(migrations.Migration):
    dependencies = [("tickets", "0005_remove_weeklyschedule_machines_and_more")]
    operations = [
        migrations.AddField(model_name="ticket", name="all_machines", field=models.BooleanField(default=False)),
        migrations.RunPython(restore_imported_all, migrations.RunPython.noop),
    ]
