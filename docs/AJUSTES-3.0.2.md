# Ajustes de revisão, geração e catálogo — 3.0.2

## Texto

O revisor local considera alguns contextos que um dicionário sozinho não distingue. O caso `Meu testo fala sobre cachorro` agora resulta em `Meu texto fala sobre cachorro.` no automático de casos seguros. O uso correto em `Eu testo o servidor.` fica preservado. Foram acrescentados início de frase com maiúscula, erros de escrita frequentes e combinações simples de concordância corrigidas em uma passagem.

O nome `Lucas Perdigão de Oliveira` e a marcação das imagens permanecem iguais. O dicionário não substitui uma análise linguística completa: palavras válidas com significado incorreto e concordâncias complexas ainda podem passar sem sugestão. Não é necessário cadastrar uma chave para usar o modo local.

Depois de aplicar correções automáticas, as sugestões que exigem aprovação continuam contadas e disponíveis. Seus trechos acompanham o deslocamento causado pelas alterações. O automático também confere um documento ao abri-lo, conforme o modo salvo. A revisão em segundo plano não abre o cartão de progresso sobre a prévia. A revisão manual continua disponível, inclusive enquanto a análise automática termina.

Desfazer revisão e Ctrl+Z recuperam o texto anterior. Mudar o modo de revisão não apaga o botão de desfazer a última correção. Alterar somente categoria ou caminhos não provoca nova revisão do mesmo texto.

## Raiz e capa

A geração e o botão Adicionar ao catálogo resolvem a raiz a partir do HTML de saída, procurando a pasta que contém `index.html`. A raiz explícita continua sendo respeitada; uma saída fora dela gera uma mensagem específica. A configuração detectada passa a ser usada pelos controles da interface.

A capa aceita um caminho relativo ao Markdown/HTML de saída, relativo à página do catálogo, relativo à raiz (`/imagens/...`) ou absoluto. Internamente, o caminho é normalizado antes de gravar os arquivos. Se dois arquivos diferentes corresponderem ao mesmo texto relativo, o formulário pede uma seleção explícita. O botão **Escolher capa** abre um seletor de imagens do servidor; o nome e a descrição preenchidos ficam preservados durante a escolha.

Ao salvar os dados da documentação, o aplicativo valida a raiz e a capa quando há destino definido. Uma capa inexistente mantém o formulário aberto com os campos preenchidos e uma mensagem no próprio formulário. Sem capa explícita, gerar e cadastrar pode usar a primeira imagem existente do documento, inclusive quando ela foi inserida como Markdown sem um registro de miniatura.

O catálogo permanece no formato original de `js/projetos-conteudo.js`. A capa e o link são gravados em relação à página que exibe esse catálogo. A publicação GitHub continua sendo uma ação com revisão separada.

## Falhas e interface

O rodapé não mantém uma indicação de geração bem-sucedida enquanto uma nova geração está falhando ou o rascunho foi alterado. Operações concluídas deixam de cobrir a prévia depois de alguns segundos; seu histórico continua em Operações. A revisão automática usa o status da barra do editor.

Uma falha de gravação do catálogo recupera os bytes do HTML anterior, inclusive quando ele usa uma codificação antiga. O processo continua preservando o template e as demais páginas do site.

## Instalar

Extraia o pacote 3.0.2 fora da pasta da instalação. Dentro da pasta extraída `SeaBirdsCloud`, como root no servidor:

```bash
bash deploy/update-app.sh
```

Depois atualize a página do navegador. A instalação local entregue pelo agente não atualiza automaticamente seu LXC ou EC2. Consulte [Validação](VALIDACAO.md) e [Revisor](REVISOR.md).
