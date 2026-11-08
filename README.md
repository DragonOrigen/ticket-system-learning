# Sistema de tickets — versão LOCAL / SQLite

Usa SQLite, sem servidor de banco e sem configuração de PostgreSQL.
Suporte, tarefas manuais, dashboard, ajuda, usuários e importação XLSX estão incluídos.
Não há repetição semanal automática.

## Iniciar no Windows (CMD)

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py preparar_sistema
python manage.py createsuperuser
python manage.py runserver
```

Abra http://127.0.0.1:8000/. O banco é db.sqlite3.
Com Conda, substitua os três primeiros comandos por:

```bat
conda env create -f environment.yml
conda activate tickets-django
```

Linux/macOS: python3.12 -m venv .venv; ative com source .venv/bin/activate.
Testes: python manage.py test. Reabra o terminal ativando o ambiente antes de iniciar.
Contas adicionais são cadastradas em /admin/. O grupo Tecnicos dá acesso aos chamados de todos.
O catálogo inicial é criado por preparar_sistema; confira as máquinas em /admin/.
Importação: veja IMPORTACAO.md. Não há contas, senhas ou dados reais no pacote.

## Atualizar a versão anterior

Pare o servidor e faça backup. Preserve db.sqlite3 e .local-secret.
Desative qualquer agendamento antigo de processar_recorrencias e exclua seu arquivo Python antigo
se copiar código sobre uma instalação existente. Execute python manage.py migrate.
A migração 0005 remove agendamentos, preservando os tickets já criados.
Os dados locais não são enviados automaticamente para a versão online.
