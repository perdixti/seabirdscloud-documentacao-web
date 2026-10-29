# Revisor de texto leve

O padrão é **Local** e **Sugerir**. Não há modelo de linguagem carregado, GPU ou envio de texto para outro serviço nesse modo. São usadas regras de português e um dicionário, carregado somente na primeira revisão.

## Usar

- **Revisar texto:** analisa a seleção ou, se não houver seleção, o documento. O limite é de 50 mil caracteres por revisão.
- **Sugerir:** mostra os resultados para você escolher. Correções por regras vêm marcadas; sugestões do dicionário e casos ambíguos precisam ser selecionados.
- **Automático (casos seguros):** aplica as correções classificadas pelas regras durante a edição.
- **Automático (todas as sugestões):** também aplica sugestões de dicionário e pontuação ambígua. Confira o resultado, especialmente termos técnicos e nomes próprios.
- **Desativada:** interrompe a revisão durante a digitação; a revisão manual continua disponível.
- **Desfazer revisão** ou **Ctrl+Z:** recupera o texto anterior em uma ação do histórico. O automático não reaplica imediatamente a mesma revisão desfeita.

As sugestões que precisam de aprovação continuam visíveis depois de uma correção automática. A barra mostra o estado da revisão; a revisão automática não abre o cartão de progresso. Documentos abertos são conferidos conforme o modo salvo. Aplicar correções não gera o HTML nem publica alterações. Se o texto mudar enquanto a revisão estiver em andamento, o resultado antigo não sobrescreve sua edição.

Em **Configurar revisor**, cadastre palavras ignoradas, como nomes de produtos ou termos próprios. Blocos de código, comandos reconhecidos, URLs, caminhos, marcação HTML e referências de imagens são protegidos da revisão.

## O que o modo local consegue corrigir

Inclui acentos e erros de escrita comuns, sugestões de dicionário, maiúscula no início de frases, espaços depois da pontuação, algumas palavras repetidas, pontuação final e padrões simples de concordância. Em contextos reconhecidos, distingue `Meu testo fala...` de `Eu testo o servidor.`. Exemplo: `Voce nao configurou a aplicacao,confira a conexao.` vira `Você não configurou a aplicação, confira a conexão.`

As regras não compreendem todo o contexto da frase. Uma palavra válida com sentido incorreto, uma vírgula dependente de interpretação ou uma concordância complexa podem passar sem sugestão. A classificação “casos seguros” reduz a intervenção, mas não garante correção linguística em todos os contextos.

O dicionário usa [pyspellchecker](https://pyspellchecker.readthedocs.io/en/latest/quickstart.html), com português e distância de edição 1, até 250 palavras desconhecidas diferentes por revisão e cache limitado. Termos técnicos conhecidos são preservados. Não é um agente generativo local.

## Consumo medido

No teste Linux da versão 3.0.2, gerador e revisor atingiram **274,2 MB de pico de memória residente**, com uma CPU disponível e limite de memória virtual de 450 MB. O cenário revisou 49 mil caracteres, criou um backup de um site com 32 MB de dados e restaurou a cópia, em 2,9 segundos no total.

O resultado indica compatibilidade com a proposta de um ambiente de 500 MB e uma CPU para o gerador e o revisor, sujeito à carga e aos demais processos do sistema. O VS Code Web/code-server é um serviço separado e não entrou nessa medição. Backups precisam de espaço em disco para arquivo temporário, cópia criptografada e recuperação.

## Revisão contextual opcional

Se desejar uma análise contextual, **Configurar revisor → OpenAI** permite salvar a chave como segredo e autorizar explicitamente o envio dos trechos. Esse modo usa uma API externa e pode gerar cobrança; a opção local continua independente dele. O campo vazio mantém a chave salva, e a ação Remover exclui a credencial configurada.

A integração usa Responses com saída estruturada, `store: false` e somente os trechos de prosa liberados pelo revisor. Não envia o template completo, imagens ou arquivos do site. `store: false` não é uma promessa de retenção zero em todos os sistemas do provedor. Consulte [saídas estruturadas](https://developers.openai.com/api/docs/guides/structured-outputs) e [Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses).

Essa integração foi validada com respostas simuladas; não foram feitas chamadas pagas nem enviado conteúdo real nesta entrega.
