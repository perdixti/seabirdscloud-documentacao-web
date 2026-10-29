# Catálogo das documentações pelo navegador

A partir da versão 2.8.0, o formulário gerencia os cards do `js/projetos-conteudo.js` do site. Ele mantém a variável `dadosCategorias`, as categorias, os comentários e o restante do JavaScript existente. A leitura analisa a estrutura do arquivo sem executar seus comandos.

## Cadastrar a documentação que acabou de gerar

1. Gere o HTML normalmente, na pasta do seu site.
2. Clique em **Adicionar ao catálogo** no editor.
3. Selecione uma categoria existente ou digite um nome novo. O nome novo cria um grupo; diferenças de maiúsculas/minúsculas não criam outra categoria igual.
4. Confira o título e o link, preenchidos a partir do documento. A primeira imagem anexada é sugerida como capa quando disponível.
5. Informe a descrição e a imagem do card. O campo de imagem também oferece os caminhos já usados no catálogo.
6. Clique em **Salvar no catálogo**.

O arquivo é alterado na cópia local do site. A ação não cria commit ou push. Depois use **Revisar publicação do site** ou o botão de publicação já existente para revisar HTML, imagens e o catálogo juntos.

## Gerenciar cadastros existentes

Em **Site e repositórios**, selecione a raiz do site e abra **Catálogo de documentações**. A lista está agrupada por categoria e permite buscar título, categoria e link. Use **Editar** para modificar um card ou mudá-lo de categoria. Campos extras existentes no objeto são preservados.

O catálogo não aceita dois cadastros apontando para a mesma página HTML. Para modificar um cadastro existente, use Editar. Se a documentação atual já estiver cadastrada, o botão do editor abre o cadastro correspondente.

**Remover do catálogo** pede confirmação e retira apenas o card; o HTML e suas imagens continuam no site. **Desfazer última alteração** restaura a versão anterior do arquivo, inclusive depois de reiniciar a aplicação. Se o arquivo foi alterado externamente, é necessário recarregar; a aplicação não sobrescreve uma edição posterior.

Cada gravação e restauração cria uma cópia anterior em `data/file-backups/` (ou `/var/lib/seabirds/file-backups/` na instalação Linux). O formulário pede confirmação antes de descartar campos editados ainda não salvos.

Para excluir também o HTML e as imagens exclusivas da documentação, use **Lixeira de páginas → Excluir definitivamente**. Veja [Exclusão completa](LIXEIRA-PAGINAS.md).

## Caminhos e formato

Os padrões do seu site são:

```text
Arquivo do catálogo:         js/projetos-conteudo.js
Página que exibe o catálogo: paginas/projetos.html
```

Os dois caminhos são relativos à raiz que contém o index.html. Se o arquivo ou a página estiver em outra subpasta, ajuste em **Arquivo e página do catálogo → Carregar catálogo**. A configuração fica salva por site. O nome do arquivo permanece `projetos-conteudo.js`.

Os campos imagem e link são resolvidos em relação à página que exibe os cards, não à pasta `js` nem ao HTML da documentação. Para `paginas/projetos.html`, o formato continua sendo:

```javascript
{
    categoria: "Linux",
    projetos: [
        {
            titulo: "Validando acesso com NGINX e SPNEGO",
            imagem: "../imagens/projetos/linux/spnego/logo.png",
            descricao: "Autenticação SPNEGO no NGINX, utilizando Samba4 como controlador de domínio (AD/DC) e Bind9 como servidor DNS.",
            link: "../projetos/linux/spnego.html"
        }
    ]
}
```

O formulário exige HTML e imagem existentes dentro do site. Aceita os arquivos de imagem já usados pela aplicação, incluindo PNG, JPEG, WebP e SVG. Caminhos físicos enviados pelo documento são convertidos para URLs relativas; espaços e acentos nos nomes dos arquivos são codificados corretamente.

Os textos do formulário são tratados como texto simples e escapados para o HTML dos cards. Aspas e caracteres especiais não interrompem o JavaScript. O arquivo deve declarar `const`, `let` ou `var dadosCategorias` com objetos e listas literais; campos calculados não são editados pelo formulário. Código e comentários fora dos dados são preservados.

## Publicar

A revisão agora também inclui o `projetos-conteudo.js` alterado, com diferença textual. Ele é pré-selecionado junto do HTML e das imagens de capa referenciadas no catálogo que tenham alterações. Outros arquivos JavaScript continuam fora dessa publicação. Arquivos já preparados no Git que não foram selecionados são preservados.

Revise os arquivos e confirme o commit/push na main. A pipeline existente continua publicando no S3; salvar o catálogo sozinho não inicia essa pipeline.

## Atualizar o servidor

Extraia o pacote 2.9.0 numa pasta nova no servidor. Na pasta `SeaBirdsCloud` extraída, como root, execute:

```bash
bash deploy/update-app.sh
```

O atualizador instala o analisador JavaScript necessário e reinicia o gerador. Preserva os dados e os arquivos do site. Depois recarregue a aplicação para receber os novos botões.
