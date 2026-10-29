# Nome, e-mail e token pelo gerenciamento web

Na versão 2.9.0, use **Site e repositórios → Configurar GitHub**. O mesmo formulário está disponível em **Clonar repositório** e na revisão de publicação. A configuração é compartilhada pelos clones, publicações e consultas de pipeline, sem reiniciar o servidor.

Preencha o nome e o e-mail que deseja usar nos commits. Cole o token no campo **Token do GitHub (segredo)** e clique em **Salvar configurações**. Não cole o texto de exemplo `COLE_O_TOKEN_REAL_AQUI`; informe o token gerado na sua conta.

Se há um repositório válido selecionado, o formulário informa qual receberá o autor. Ao salvar, configura `user.name` e `user.email` somente nesse clone. O nome e o e-mail também ficam como padrão para novos clones e publicações cujo Git ainda não tem autor. Identidades específicas já existentes em outros clones são preservadas.

Na revisão de publicação, **Configurar autor e GitHub** permite corrigir um autor ausente sem perder a seleção dos arquivos ou a mensagem do commit. Salvar configurações não cria commits nem faz push.

## Token como segredo

- O campo usa entrada de senha. Ao reabrir, ele fica vazio e mostra apenas se existe um token configurado.
- Deixe o campo vazio para manter o token atual. Cole outro para substituí-lo.
- **Remover token** pede confirmação, apaga o segredo salvo pela aplicação e impede que ela reutilize automaticamente `SEABIRDS_GITHUB_TOKEN` do ambiente. Não revoga o token na conta do GitHub; SSH e outras credenciais Git existentes continuam sendo independentes.
- Se nunca foi salvo/removido um token pela web, a variável `SEABIRDS_GITHUB_TOKEN` existente continua funcionando. O token salvo pela web tem prioridade.
- A API não devolve o token, sua parte final, o texto criptografado ou a chave. Erros de validação desse formulário também não devolvem os valores enviados.
- O token não entra em documentos, autosaves, URLs ou argumentos do Git. É fornecido ao helper de autenticação pelo ambiente do processo filho.

No Linux instalado, os dados ficam em `/var/lib/seabirds/secrets/github.json`, criptografados com Fernet, e a chave fica em `/var/lib/seabirds/secrets/github.key`. Os arquivos usam modo 0600 e a pasta usa 0700. No Windows, ficam em `data/secrets/` dentro dos dados da aplicação, protegidos também pelas permissões do perfil do usuário. A criptografia não impede acesso por um administrador ou processo que tenha acesso à chave e ao arquivo.

Guarde o arquivo e a chave juntos no backup privado dos dados para migrar ao LXC. Não publique esses arquivos no repositório do site. Os ZIPs de distribuição não incluem dados ou segredos. Se perder a chave, abra o formulário e salve um novo token; não é necessário reinstalar o aplicativo.

O ambiente de desenvolvimento atual usa HTTP. O campo mascarado e o armazenamento criptografado não criptografam o transporte: ao colar e salvar um token por HTTP, ele trafega sem TLS. A tela informa isso. Para proteger esse envio, use HTTPS.

## Permissões no GitHub

Crie um token fine-grained restrito a `perdixti/SeaBirdsCloud-site`, com **Contents: leitura e gravação** para clonar/publicar e **Actions: leitura** para consultar a pipeline. O token precisa pertencer a uma conta com acesso ao repositório e continuar válido. Não é a senha da conta GitHub. Consulte a [documentação do GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

## Atualizar o servidor existente

Extraia o pacote 2.9.0 numa pasta nova no servidor. Entre na pasta `SeaBirdsCloud` extraída e, como root na console do servidor, execute:

```bash
bash deploy/update-app.sh
```

O atualizador instala a nova dependência de criptografia, guarda o código anterior e reinicia o gerador. Preserva o site, os rascunhos, as configurações dos serviços e os segredos existentes. Não basta copiar os arquivos Python desta versão sem atualizar as dependências.

Depois, recarregue a aplicação e abra **Configurar GitHub**. Não é necessário executar comandos para configurar o autor ou o token nas próximas alterações.
