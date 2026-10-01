# Testes manuais do chat (Home do backoffice)

Lista de pedidos para testar o assistente à mão, com o resultado esperado. Corre-se no **demo-ai-lab**, nunca num site de cliente.

**Antes de começar**
- **Código novo:** no manager, faz **Stop** e depois **Start** do `demo-ai-lab`, porque o servidor só lê o código novo ao arrancar.
- **Onde testar:** abre http://localhost:8134/backoffice/ e começa uma conversa nova em **+ New conversation** para cada grupo de testes, salvo indicação em contrário.
- **Emails:** neste demo os emails não saem. Aparecem no **Server Log** do site no manager (ou em `demo-ai-lab/.server.log`).
- **Depois de cada teste que muda o site:** carrega em **Undo this** para deixar o demo como estava, salvo se o teste disser outra coisa.

**Como marcar:** `[x]` passou · `[!]` passou com reparos (escreve-os por baixo) · `[ ]` falhou.

---

## 1. Respostas e botões

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `Que secções tem a página Reservas?` | Lista as 5 secções (`reservas-hero`, `reserva`, `grupos`, `boas-praticas`, `contactos`). Por baixo, os botões **View Reservas** e **Edit Reservas**. Não muda nada, por isso não há **Undo this**. |
| [ ] | `Onde é que carrego a foto da capa do livro?` | Manda para `/backoffice/media/`. O caminho é clicável no texto e aparece o botão **Media library**. |
| [ ] | Clica em **View Reservas** e depois em **Edit Reservas** | Abrem num separador novo: a página pública e a mesma página no editor. A conversa fica aberta. |
| [ ] | Abre uma conversa antiga, por exemplo http://localhost:8134/backoffice/?session=11 | As respostas antigas também mostram botões, só das páginas de que falam (sem uma lista de páginas apenas consultadas). |
| [ ] | Em qualquer resposta | Não aparecem "(ID: 3)" nem URLs completos no texto. As páginas aparecem a **negrito**. |

## 2. Perguntar quando há dúvida

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `Muda a cor dos botões.` | Não muda nada. Faz **uma** pergunta curta (que cor? todos ou só os principais?). |
| [ ] | (mesma conversa) `Em todas as páginas, para o dourado da marca.` | Muda os botões principais para dourado em várias páginas (e no cabeçalho), numa só resposta. O resumo diz onde mudou e onde já estava dourado. Por baixo: **Changed: …**, **Undo this** e botões para as páginas. |
| [ ] | `Tira a galeria.` (conversa nova) | Pergunta qual, porque há galeria na **Início** e na **Proposta 1**, ou pede confirmação dizendo de que página. Não apaga nada sem confirmares. |
| [ ] | (mesma conversa) `A da proposta 1.` | Pede confirmação para apagar a galeria da **Proposta 1 — Clássica**. Só apaga depois de responderes `sim`. |

## 3. Secções e estilos numa página

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `Na página Reservas, acrescenta uma secção de perguntas frequentes com 5 perguntas sobre reservas de grupos, antes dos contactos.` | Nova secção logo **antes** de `contactos`, não no fim da página. Em EN aparece traduzida; as outras secções ficam iguais nas duas línguas. Demora cerca de 1 minuto. |
| [ ] | `Na Início, põe o título da secção do chef maior e em itálico.` | Muda só esse título, sem gerar a secção de novo. Responde depressa (poucos segundos) e o resto da secção não muda. |
| [ ] | `Na Proposta 2, a secção livro deve ter uma zona para a imagem da capa à esquerda.` | Refaz só a secção `livro`. O texto fica **só em português** (sem PT e EN lado a lado); o EN é a tradução. |

## 4. Várias páginas no mesmo pedido

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `Nas três propostas, acrescenta uma faixa com o horário antes dos contactos: terça a sábado, 12h30–15h e 19h–22h30; fechado ao domingo e à segunda.` | Uma resposta só. Faixa nova antes de `contactos` na **Proposta 1**, **2** e **3**, com exatamente esse horário (nada inventado). Botões View/Edit para as três páginas. |
| [ ] | (mesma conversa) `Desfaz isso.` | Responde que desfez nas três páginas. As três ficam exatamente como antes. |
| [ ] | `Em todas as páginas que têm a secção de contactos, põe o título dessa secção em maiúsculas.` | Muda o título em todas as páginas com `contactos` (5) e diz se alguma já estava em maiúsculas. Sem "I ran out of steps". |
| [ ] | `Em todas as propostas, põe os botões com cantos redondos.` | Muda os botões das três propostas numa só resposta, sem mexer nas outras páginas. |

## 5. Sliders e galerias

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `Na Proposta 2, no slider do foie gras, põe a foto da equipa a empratar em primeiro.` | Em poucos segundos, sem IA a redesenhar. No slider `foto-foie` a foto da equipa passa a 1.ª; as outras 5 mantêm a ordem; igual em EN. |
| [ ] | `Na Proposta 1, tira a segunda foto da galeria.` | A galeria fica com 5 fotos, a 2.ª ("A sala do CHECKin…") desaparece, em PT e EN. |
| [ ] | `Na Proposta 3, troca a primeira foto do slider do topo por uma foto da sala.` | Procura na biblioteca, troca só essa foto e o texto alternativo fica certo em cada língua. |

## 6. Fotos e fundos

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `Na página Reservas, procura uma foto melhor para o fundo do topo: algo com a sala do restaurante.` | Não muda nada ainda. Mostra miniaturas clicáveis, da biblioteca e do Unsplash (estas com a etiqueta "Unsplash"). |
| [ ] | Clica numa miniatura **da biblioteca** | Envia "Usa a foto lib:…" e põe essa foto no fundo de `reservas-hero`, em PT e EN. Se havia uma camada escura por cima, mantém-se. |
| [ ] | Repete e clica numa miniatura **Unsplash** | A foto é copiada para a biblioteca (aparece em Media, com o crédito do fotógrafo) e fica no fundo. |
| [ ] | No editor (**Edit Reservas**), clica numa imagem e abre o seletor de imagens | Há um separador **Unsplash**. Pesquisar em inglês (ex.: `sea terrace`) mostra fotos; ao escolher, a foto entra na biblioteca e é aplicada. |

## 7. Formulários e contactos

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `Testa o formulário de reservas.` | Diz que o formulário foi validado, gravado e que os emails (notificação e confirmação) foram enviados **só para geral@portugalwebdesign.pt**, com `[TESTE]` no assunto. No Server Log vês os 2 emails. Em **Forms → submissions** não fica nenhuma submissão de teste. |
| [ ] | `Os formulários do site estão todos a funcionar?` | Testa os formulários usados nas páginas e diz o resultado de cada um. Nenhum email vai para o cliente. |
| [ ] | `Verifica se os contactos do site estão certos.` | Não muda nada. Diz que o fixo **+351 289 824 178** aparece em ~14 sítios e nas Definições está o telemóvel **+351 968 070 776**. Mostra o botão **Contact settings**. **Não** diz que algo foi "confirmado na web" sem ter pesquisado. |
| [ ] | `Compara os contactos com o que aparece na internet.` | Faz a pesquisa e cita as fontes (links). Pergunta antes de corrigir o que quer que seja. |

## 8. Factos e pesquisa na web

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `O chef lançou um livro novo. Que livro é e quem são os coautores?` | Pesquisa na web e responde com as fontes no fim. Não inventa nomes nem datas. |
| [ ] | `Acrescenta à página Início uma secção com os prémios do restaurante.` | Pesquisa ou pergunta antes. O que não conseguir confirmar aparece como `[confirmar]`, nunca inventado. |

## 9. Desfazer

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | Qualquer pedido que mude uma página, depois **Undo this** | A página volta ao estado anterior em todas as línguas. A resposta fica marcada "Undone: …" e o botão desaparece. |
| [ ] | Um pedido que mude uma página e depois `volta atrás` | Igual, pelo chat. |
| [ ] | Um pedido que mude a **Início**; depois edita essa página no editor e grava; depois **Undo this** no chat | **Pergunta** antes, a dizer que a página mudou desde então. Só desfaz (e perde a edição do editor) se confirmares. |
| [ ] | Igual ao anterior, mas pelo chat: `desfaz isso` | Explica o que se perdia e pede confirmação. Não força sozinho; só desfaz depois de `sim`. |
| [ ] | Um pedido que mude uma página; no editor, carrega em **Undo** | O Undo do editor volta ao ponto antes do pedido do assistente, de uma vez. |
| [ ] | `Muda o telefone de contacto para +351 912 345 678.`, depois **Undo this** | O telefone volta ao anterior. Se entretanto mudaste outra coisa nas Definições (ex.: o email), essa outra mudança **fica**. |

## 10. Parar, editar, anexos

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | Envia um pedido grande e carrega em **■** (ou Esc) enquanto pensa | Pára. Diz "Stopped. Nothing was changed.", ou o que já tinha mudado, que podes desfazer. |
| [ ] | Na tua última mensagem, carrega em **Edit**, muda o texto e envia | A resposta antiga é substituída. Se ela tinha mudado o site, essas mudanças são desfeitas primeiro. Se entretanto editaste a mesma página, recusa e pede-te uma mensagem nova. |
| [ ] | Arrasta uma imagem para a caixa (ou cola) e pergunta `Que cores vês nesta imagem? Não alteres nada.` | Descreve a imagem. Não muda nada. |
| [ ] | Anexa um PDF com um menu e pede `Usa este PDF para atualizar a secção da carta na Proposta 2.` | Usa os pratos e preços do PDF, sem inventar outros. Só a secção `carta` muda. |

## 11. Pedidos longos

| ✓ | Pedido | Resultado esperado |
|---|---|---|
| [ ] | `Revê todas as páginas e põe todos os títulos de secção com o mesmo estilo dos da Início.` | Ou faz tudo, ou faz parte e diz claramente o que fez e o que ficou por fazer (e que podes pedir para continuar). Nunca acaba só com "I ran out of steps". Um único **Undo this** desfaz tudo o que fez. |

---

**O que reportar quando algo falha**
- o número do teste e o link da conversa (`?session=…`);
- o que esperavas e o que aconteceu;
- se mudou algo que não devia (que página e secção).
