# Backup completo e restauração pelo navegador

Em **Backups**, configure uma senha com pelo menos 12 caracteres. Você pode criar uma cópia imediatamente ou habilitar o agendamento, de 1 a 168 horas. O serviço precisa continuar em execução para realizar backups agendados.

## Conteúdo

O arquivo `.sbbak` inclui o banco de rascunhos, históricos, fontes, configurações da aplicação, segredos, lixeiras e arquivos dos **sites cadastrados**, inclusive os metadados `.git` dos clones. O painel lista as pastas incluídas. Cadastre a raiz em **Site e repositórios** para incluir um site; uma pasta externa que não estiver cadastrada não entra automaticamente.

Não inclui configuração do sistema operacional, unidades systemd, proxy ou `/etc/seabirds`. Continue guardando uma cópia separada dessas configurações para reconstruir um servidor. Caches, ambientes Python, `node_modules`, a fila de operações e outros backups são excluídos.

O banco usa cópia consistente do SQLite. Os arquivos são processados em blocos, sem carregar o arquivo inteiro em memória. Cada cópia é criptografada com AES-256-GCM e uma chave derivada da senha. Há um manifesto de integridade verificado na restauração. Guarde a senha fora do servidor: a perda dela impede abrir a cópia baixada.

## Guardar e importar

Use **Baixar** e mantenha uma cópia fora da máquina. Guardar somente no mesmo disco não protege contra a perda do servidor. A senha configurada para agendamento é armazenada criptografada na instalação; não é devolvida ao navegador.

**Importar para restaurar** recebe um arquivo `.sbbak` de até 3 GB. A inspeção e restauração admitem até 2 GB de conteúdo descompactado e 50 mil arquivos. Esses limites também se aplicam à criação. É necessário espaço livre para os temporários e para uma cópia de recuperação. Importar registra o arquivo, mas não o restaura.

A retenção configurada remove somente backups agendados antigos. Cópias manuais, importadas e de recuperação ficam preservadas.

## Restaurar

1. Clique em **Restaurar** e informe a senha da cópia.
2. Confira os destinos. Para migrar de Windows para Linux, associe cada raiz antiga à pasta correspondente no servidor novo, como `/srv/seabirds/SeaBirdsCloud-site`.
3. Revise o resumo e confirme a restauração. Antes de alterar arquivos, o aplicativo cria uma cópia de recuperação do estado atual.
4. Aguarde a conclusão no painel de operações e recarregue a aplicação conforme indicado.

Os arquivos presentes na cópia substituem seus equivalentes. **Arquivos adicionais do destino são preservados**: não é uma limpeza nem um espelhamento com exclusão. Caminhos registrados nos rascunhos e configurações são adaptados aos destinos escolhidos. Os serviços e a senha de acesso do servidor atual são mantidos; o agendamento restaurado fica desativado até uma nova conferência.

Falhas tratadas durante a gravação tentam recuperar o estado anterior. Se o processo for interrompido abruptamente, o painel informa a restauração interrompida e identifica a cópia de recuperação. Confira os arquivos antes de repetir e preserve essa cópia.

Evite editar os mesmos arquivos por outro programa durante a cópia ou restauração. O aplicativo bloqueia ações concorrentes da própria interface durante a manutenção, mas não bloqueia editores e processos externos.
