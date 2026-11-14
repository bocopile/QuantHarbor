# Q27 실제 위험 검사 준비 보완

원래 scenario24/25는 admission challenge 저장 때 공통 현재68+미래63=131행으로128행가드가거부했다. bytes합6352989는8MiB이하다. 자기합성DB의guard에NOTICE만추가한진단이며가드/한도우회·저장소변경은없었다. [계측](../evidence/execution-resume-common-budget-measure-2026-10-30.json).

최종준비는기존보유4개인첫종목에서0.5개×400의실제매수/매도를각각기장한다. 현금은settled600/payable-200/receivable200,독립brokercapacity600이고미반영payable200을차감한다. 불필요한매수결제사건을넣지않아공통기록을줄이되,기존예약매도3.5와정산가능수량3.5를보존한다. 실제gross400·active350·new300·total1050/NAV1000·turnover1.05는불변이며현금가능액400에서신규300이현금부족때문에먼저차단되지않는것도검사한다. 실제current_risk/prospective_loss/turnover함수호출assert는유지했다. [제안별실패이력후a04성공](../evidence/execution-resume-risk-fixture-fixed-a04-2026-10-30.json).

초기안은미정산매수로settledquantity음수가되거나brokercapacity에서payable을이중차감해의도한위험계산까지도달하지못했고,정확available300을가정한추가oracle도틀렸다. 해당실패를성공으로바꾸지않고마지막준비의독립실제수치와보호가드를대조한다. 기존경제코드/권한/용량/기준fixture40/원래84시나리오는약화하지않았다.

다른보강은aborted_unsent·새generation뒤같은candidate재승인도재admit거부,같은command의다른approval payload가replay_conflict이며추가intent없음을원래함수에추가한다. 보강2사례는하루경과unknown/예약/옛authority거부와consume+cursor/workstate의commit장애rollback/중복noop이며원래84뒤85/86으로추가했다. 날짜검사는금융intent·예약·send불변을검사하며만료명령의정당한종료receipt/audit저장까지금지하지않는다. 원래0인fee/taxhold도양수로가정하지않고기존component값일치와양수hold존재를확인한다.

최신원래checkout의바뀐3함수/추가2함수를실제로6context에서465.254초PASS·전후선택source불변·자기DB6개정리했다. [최신집중](../evidence/execution-resume-current-focused-a01-2026-10-30.json). runner단위6·공개품질701지적0도확인했다. 전체86/최신제품전체/고정40최종독립판정은별도관문이며본작업만으로Q27완료가아니다.
