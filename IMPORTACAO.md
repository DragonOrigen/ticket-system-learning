# Importar a planilha antiga (.xlsx)


O comando importa a aba `Sistema de Tickets` no formato do exemplo recebido.
A aba de inventário e as instruções à direita são ignoradas. Linhas sem descrição são ignoradas.
Não modifica a planilha e não cria contas ou máquinas automaticamente.

1. Pare o servidor, faça backup de db.sqlite3 e preserve .local-secret ao atualizar o código.
2. Ative venv ou Conda. Execute `python -m pip install -r requirements.txt` e `python manage.py migrate`.
3. Cadastre as contas e as máquinas no admin. `python manage.py preparar_sistema` pode criar o catálogo inicial,
   mas confira se corresponde às máquinas reais antes de importar tickets com Todas.
4. Copie `mapa_importacao.exemplo.json` para `mapa_importacao.json`. Nos valores de usuarios,
   coloque os nomes de login exatos das contas existentes. Alex e Felipe à esquerda são os nomes da planilha.
5. Copie o XLSX para a pasta do manage.py e simule:

```bat
python manage.py importar_tickets "Sistema de Tickets(1).xlsx" --mapa mapa_importacao.json --simular
```

Se a simulação estiver correta, execute sem --simular:

```bat
python manage.py importar_tickets "Sistema de Tickets(1).xlsx" --mapa mapa_importacao.json
```

Qualquer erro de validação impede toda a importação e indica a linha a corrigir.
Erros durante a gravação também desfazem toda a operação. A simulação não grava dados.
O terminal informa os novos registros, os ignorados, os já importados e os erros.

### Equipamentos e duplicatas

- `Todas` significa todas as máquinas cadastradas, inclusive desativadas, no momento da importação.
  É um conjunto fixo: máquinas cadastradas depois não são acrescentadas a tickets antigos.
- Várias máquinas específicas podem ser separadas por ponto e vírgula, vírgula ou quebra de linha.
  A palavra Várias sozinha não identifica quais são e gera erro.
- Campo vazio significa Sem equipamento. Equipamentos desconhecidos precisam ser cadastrados ou mapeados.
- Em `maquinas` no JSON, use, por exemplo, `"ingles-1": "Máquina Inglês 01"` se os nomes forem diferentes.
  O valor à direita precisa existir no cadastro. Deixe vazio quando os nomes já coincidem.
- O ID original fica separado do ID novo, evitando colisões com tickets existentes.
  A combinação origem + ID original evita duplicatas. Reimportar não sobrescreve tickets já importados.
- A origem padrão é `planilha-tickets`. Mantenha a mesma origem nas reimportações, mesmo renomeando o XLSX.
  Use `--origem outra-unidade` somente para uma fonte realmente independente.

### Datas e histórico

A data de abertura é preservada no fuso do sistema (America/Sao_Paulo).
Sem horário na origem, usa 00:00. A última atualização registra a importação, pois a antiga não consta no arquivo.
Data de conclusão fica desconhecida, mesmo nos resolvidos. Observações e respostas ficam numa seção própria,
sem autoria ou data inventadas. Categoria inicial: Suporte geral; reclassifique depois pela edição.
Tarefas são abertas manualmente. Não há recorrência automática.

Código: tickets/import_spreadsheet.py valida a leitura; management/commands/importar_tickets.py
coordena a simulação e a gravação; SpreadsheetImport guarda a referência e o histórico legado.
