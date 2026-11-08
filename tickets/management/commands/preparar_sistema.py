from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from tickets.models import Machine


class Command(BaseCommand):
    help = "Cria o grupo Tecnicos e o catálogo inicial, sem criar usuários ou senhas."

    def handle(self, *args, **options):
        Group.objects.get_or_create(name="Tecnicos")
        names = [f"Máquina {i:02}" for i in range(1, 25)]
        names += [f"ingles-{i}" for i in range(1, 6)] + ["ingles-prof", "Máquina do Educador"]
        for name in names:
            Machine.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("Grupo e máquinas preparados."))
