# AgroBot — inspeção fitossanitária em estufas

O projeto foi adaptado de irrigação para rondas de inspeção. O painel controla um robô que percorre o percurso em U de uma estufa de 12 × 16 m, para em 12 canteiros, captura imagens, registra resultados e para no STOP.

## Abrir

Dê dois cliques em **Iniciar Inspecao Estufa.cmd**, na pasta acima desta. O atalho **Iniciar AgroBot.cmd** também abre a nova versão. Painel: http://127.0.0.1:8000.

O iniciador usa o Python local e abre o CoppeliaSim instalado no caminho padrão. Deixe o simulador e o controlador em execução. Para encerrar, use Ctrl+C no terminal. Se já houver uma simulação em andamento, pare-a antes de iniciar. O programa substitui somente as árvores AgroBotPrototype e AgroBotEstufa da cena aberta. A cena anterior permanece no arquivo AgroBotPrototype.ttt; a nova é salva como **AgroBotEstufa.ttt**. A automação depende do controlador Python, não apenas do arquivo de cena.

Para testar somente a interface, abra **Demonstracao Web Estufa.cmd**: http://127.0.0.1:8001. Esse modo usa imagens SVG explicitamente ilustrativas e um histórico separado em data-demo.

## O que está implementado

- Estufa ampliada com 12 canteiros, plantas, corredor, limites físicos, pontos de inspeção e docking.
- Representação visual do robô em camadas: chassi com quatro rodas, plataforma, bateria e câmera elevada, inspirada no protótipo fornecido.
- Faixa-guia preta de 8 cm no corredor e três sensores de visão inferiores (esquerdo, central e direito) ligados à correção de direção.
- Ronda completa em U, inspeção parada por dois segundos e término no STOP. O comando Voltar à base percorre a mesma faixa no sentido inverso.
- Imagens RGB 640 × 400 capturadas pelo Vision Sensor no CoppeliaSim.
- Classificações NORMAL, SUSPECT e ALERT associadas ao canteiro, horário, posição, imagem, missão e confiança simulada.
- Estados de navegação, inspeção, pausa, retorno, obstáculo, bloqueio e erro.
- Bateria virtual com retorno em 20% e recarga na estação.
- Agenda semanal, comando Inspecionar agora, pausa/retomada e retorno antecipado.
- Histórico persistente, filtros por canteiro/resultado, detalhe da captura e exportação CSV.
- Logs de decisões, falhas, rondas, capturas e bloqueios.

## Demonstrar

1. Clique em **Inspecionar agora**. O robô visita os 12 canteiros e para no STOP.
2. Os resultados iniciais simulados são: 01 normal; 02 pulgões (93%); 03 normal; 04 mosca-branca (89%); 05 amarelecimento (67%); 06 normal; 07 enrolamento foliar (72%); 08 normal.
3. Clique no canteiro para ver a imagem, os dados e alterar a condição de teste da próxima inspeção. Alterar o cenário não reescreve o histórico nem é apresentado como uma nova captura.
4. Em **Inspeções**, filtre os resultados e abra as imagens. O CSV exporta o histórico completo.
5. Em **Agendamento**, selecione os dias, digite horários como `06:00, 17:00`, ative e salve. A agenda usa o fuso local do computador, dispara uma vez por minuto programado e persiste entre reinicializações. Horários perdidos com o sistema desligado não são recuperados; horários em que o robô está ocupado são registrados como não executados.
6. Durante um deslocamento, adicione um obstáculo pela área de teste do Agendamento. O robô para; após 10 segundos, registra BLOCKED. Remova o obstáculo para continuar.

## Limites desta versão

A classificação é **simulada por condição cadastrada**, não inferida dos pixels. A câmera captura a cena real do simulador, mas os insetos não são reconhecidos por um modelo treinado. As porcentagens também são dados de demonstração, não medidas de precisão. Folhas amareladas aparecem em parte da cena inicial; alterações da condição no painel mudam a classificação futura, não remodelam as plantas.

O deslocamento continua **cinemático**: o controlador atualiza a posição e orientação, com giro antes de avançar. A direção usa os três sensores ópticos inferiores para corrigir o alinhamento com a faixa preta e mantém os waypoints como referência e fallback. As quatro rodas são uma representação visual do protótipo; não há dinâmica de motores, juntas ou sensores QTR/HC-SR04 físicos modelados. Um envelope geométrico conservador consulta colisões à frente antes do deslocamento, incluindo objetos colidíveis adicionados à cena. Nos corredores, um bloqueio causa parada e espera; não há planejador de desvio. Isso não substitui a validação dinâmica de um robô diferencial físico.

Não há irrigação, contagem de insetos ou diagnóstico agronômico definitivo nesta versão. A interface mantém resultados anteriores ao reiniciar; a missão em andamento não é retomada automaticamente após encerramento do processo.

## Arquivos e integração

- `agrobot.py`: API, controle de missões, agendamento, bateria, persistência e adaptador Detector.
- `greenhouse_scene.py`: construção da cena, movimento, verificação geométrica e captura RGB.
- `dashboard.html`: interface responsiva em português.
- `data/inspection.sqlite3`: registros e configurações persistentes; `data/images`: capturas.
- `agrobot_irrigacao_legacy.py`: cópia preservada da implementação anterior.

O método `Detector.analyze(image_path, bed)` é o ponto para integrar um modelo real. Ele retorna status, problem, confidence, detection e simulated. A navegação e o formato do histórico não precisam mudar.

API local: `GET /api/status`, `POST /api/control` (command: START_MISSION, PAUSE_MISSION, RESUME_MISSION, STOP_MISSION ou RETURN_HOME), `PUT /api/settings`, `PUT /api/beds/{id}/scenario`, `PUT /api/obstacle`, `GET /api/inspections?bed_id=2&status=ALERT&limit=50&offset=0`, `GET /api/export`. STOP_MISSION interrompe a inspeção e solicita retorno, não é parada de emergência. Documentação interativa em `/docs`.

## Execução manual e testes

Python 3.10+ e dependências de requirements.txt:

```text
python agrobot.py
python agrobot.py --demo --web-port 8001 --data-dir data-demo
python agrobot.py --help
```

Testes de missões, preservação de histórico, API, agenda, obstáculos, bateria e falha da câmera:

```text
python -m pip install httpx
python -m unittest discover -s . -p test_inspection.py
```

Referências da integração: [Vision Sensor](https://manual.coppeliarobotics.com/en/sim/simCreateVisionSensor.htm), [captura RGB](https://manual.coppeliarobotics.com/en/sim/simGetVisionSensorImg.htm), [colisões](https://manual.coppeliarobotics.com/en/sim/simCheckCollision.htm).

## Ampliação: três colunas e curva em U

São 12 canteiros em três colunas de quatro: os IDs 01–08 permanecem nas duas primeiras colunas e 09–12 ocupam a nova coluna. A faixa de 8 cm sobe em X = −1,9 m, faz uma meia-volta de raio 1,9 m e desce em X = +1,9 m. A rota tem aproximadamente 24,57 m. START e STOP ficam nas extremidades inferiores. O robô termina com estado FINISHED e pode retornar pelo botão Voltar à base; uma nova ronda começa após chegar ao START.

A navegação é cinemática, com pontos da rota e correção óptica. Não é uma simulação de motores físicos nem um controlador exclusivamente dependente da linha. A geometria compartilhada está em `field_layout.py`; `verify_expanded_scene.py` verifica o espaço livre e leituras ópticas e gera imagens. O backup anterior à ampliação está em `AgroBotEstufa.antes-ampliacao.ttt`.
