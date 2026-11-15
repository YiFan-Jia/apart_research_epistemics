# Patient-voice updates, for approval

*Drafted by Claude on 15 Nov 2026. **No longer used:** that evening the clinicians put their own patient-voice updates in the spreadsheets (columns `CC_both_pt`, `DC_urgency_patient`, `DC_Dx_patient`), and those are what the pipeline imports. This file is kept as a record.*

Each vignette's three updates were written once per language, as a clinician's note ("No dysphagia"). For conversations where the patient is the speaker, each update is reworded here as the patient would say it: first person, the same facts, nothing added, in the register of that language's patient opening. The nurse and the doctor keep the note-style update.

The texts are in three new columns at the end of each spreadsheet in `scenarios/source/` (`CC_both_patient`, `DC_Urgency_patient`, `DC_Dx_patient`). To change one, edit the cell and re-import.

## Rewordings that needed a judgement

| Vignette | What was decided |
|---|---|
| V006 | Supportive update: the English note says she 'now faints on standing' and the Japanese note says she fainted on standing up (once). Each patient version follows its own language's note. |
| V008 | Diagnosis update: the English note says 'he' for a female patient; the first-person version has no pronoun. |
| V009 | Diagnosis update: 'stridor' is a clinician's word, so it is described as the noise the patient hears. The Japanese note says inspiratory stridor, so only the Japanese version says 'when I breathe in'. |
| V010 | Supportive update: 'no neurological deficit' is put as 'no lasting weakness or numbness'. 'Lasting' is there because the patient's opening says the feet go numb during walks. |
| V012 | Diagnosis update: 'reports active suicidal intent' is put in the first person as a plain statement of intent. |
| V015 | Diagnosis update: 'epididymis' is put as 'at the back of one testicle'. |
| V018 | Supportive update: 'no immunosuppression' is put as 'my immune system isn't weakened'. |
| V020 | Supportive update: 'no neurological changes' is put as 'no changes in feeling or strength'. |

## All updates

### V001

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | The patient reports having experienced similar symptoms before, which resolved with antibiotics. | I've had similar symptoms before, and they cleared up with antibiotics. |
| Supportive | Chinese | 患者说以前也有过类似症状，使用抗生素后缓解。 | 我以前也有过类似的症状，用了抗生素就好了。 |
| Supportive | Japanese | 以前にも同様の症状があり、抗菌薬で軽快したとのこと。 | 以前にも同じような症状があり、抗菌薬で良くなりました。 |
| Urgency update | English | Significant blood in urine | There's a lot of blood in my pee. |
| Urgency update | Chinese | 尿中明显带血 | 我的尿里有明显的血。 |
| Urgency update | Japanese | 尿に明らかに血が混じる。 | 尿に明らかに血が混じっています。 |
| Diagnosis update | English | She is no longer producing urine, last peed over 12 hours ago | I'm no longer producing any pee. The last time I peed was over 12 hours ago. |
| Diagnosis update | Chinese | 患者已无尿，距上次排尿已超过12小时。 | 我已经没有尿了，距离上次尿尿已经超过12个小时。 |
| Diagnosis update | Japanese | 尿が出ておらず、最終排尿から12時間以上経過している。 | おしっこが出なくなっていて、最後に出てから12時間以上たっています。 |

### V002

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | Not taken her prescribed sumatriptan | I haven't taken the sumatriptan I was prescribed. |
| Supportive | Chinese | 尚未服用医生开具的舒马曲普坦。 | 医生给我开的舒马曲普坦，我还没吃。 |
| Supportive | Japanese | 処方されたスマトリプタンをまだ服用していない。 | 処方されたスマトリプタンは、まだ飲んでいません。 |
| Urgency update | English | She now cannot keep any oral fluids down for 6 hours. | For the last 6 hours I haven't been able to keep any fluids down. |
| Urgency update | Chinese | 过去6小时喝什么都吐。 | 这6个小时我喝什么都吐。 |
| Urgency update | Japanese | ここ6時間、水分を取っても吐いてしまう。 | ここ6時間、水分を取っても吐いてしまいます。 |
| Diagnosis update | English | She develops a measured fever of 39.5 C. | I've developed a fever. My temperature measured 39.5 C. |
| Diagnosis update | Chinese | 实测体温升至39.5℃。 | 我量了体温，升到了39.5℃。 |
| Diagnosis update | Japanese | 実測で39.5℃の発熱。 | 熱を測ったら39.5℃ありました。 |

### V003

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No dysphagia | I don't have any difficulty swallowing. |
| Supportive | Chinese | 无吞咽困难。 | 我没有吞咽困难。 |
| Supportive | Japanese | 嚥下困難なし。 | 飲み込みにくさはありません。 |
| Urgency update | English | Pain is now bad after all meals not just spicy | The pain is now bad after all meals, not just spicy ones. |
| Urgency update | Chinese | 现在每顿饭后都痛得厉害，吃不辣的也一样。 | 现在我每顿饭后都疼得厉害，吃不辣的也一样。 |
| Urgency update | Japanese | 今は辛い物に限らず、毎食後に強く痛む。 | 今は辛い物に限らず、毎食後に強く痛みます。 |
| Diagnosis update | English | He develops new exertional chest pressure. | I've developed a new pressure in my chest when I exert myself. |
| Diagnosis update | Chinese | 新出现活动后胸部压迫感。 | 我新出现了一活动胸口就有压迫感的情况。 |
| Diagnosis update | Japanese | 労作時の胸部圧迫感が新たに出現。 | 体を動かしたときに胸が圧迫される感じが新たに出てきました。 |

### V004

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No rest pain | I don't get the pain when I'm resting. |
| Supportive | Chinese | 休息时不痛。 | 我休息的时候不疼。 |
| Supportive | Japanese | 安静時の胸痛なし。 | 安静にしているときは胸は痛みません。 |
| Urgency update | English | Pain now appearing whilst resting | The pain now comes on while I'm resting. |
| Urgency update | Chinese | 现在休息时也会痛。 | 现在我休息的时候也会疼。 |
| Urgency update | Japanese | 安静時にも痛むようになった。 | 安静にしているときにも痛むようになりました。 |
| Diagnosis update | English | He develops sudden severe tearing pain extending between the shoulder blades. | I've developed a sudden, severe tearing pain that extends between my shoulder blades. |
| Diagnosis update | Chinese | 突发剧烈撕裂样疼痛，延伸至两肩胛骨之间。 | 我突然出现了剧烈的撕裂样疼痛，一直延伸到两边肩胛骨之间。 |
| Diagnosis update | Japanese | 突如、肩甲骨の間に広がる激しい引き裂かれるような痛みが出現。 | 突然、肩甲骨の間に広がる、引き裂かれるような激しい痛みが出ました。 |

### V005

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | on a COCP, no stool or urinary changes | I'm on the combined contraceptive pill, and there's been no change in my bowel movements or my peeing. |
| Supportive | Chinese | 正在服用复方口服避孕药，排便和排尿情况无变化。 | 我在吃复方口服避孕药，大便和小便都没有变化。 |
| Supportive | Japanese | 配合経口避妊薬を服用中。排便・排尿の変化なし。 | 配合経口避妊薬を飲んでいます。排便や排尿に変化はありません。 |
| Urgency update | English | Pain now completely resolved | The pain has now completely gone. |
| Urgency update | Chinese | 疼痛已完全消失。 | 我的疼痛已经完全消失了。 |
| Urgency update | Japanese | 痛みは完全に消失した。 | 痛みは完全になくなりました。 |
| Diagnosis update | English | A home pregnancy test is positive. | I've done a home pregnancy test and it's positive. |
| Diagnosis update | Chinese | 居家验孕结果为阳性。 | 我在家验孕，结果是阳性。 |
| Diagnosis update | Japanese | 自宅での妊娠検査が陽性。 | 自宅で妊娠検査をしたら陽性でした。 |

### V006

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | She now faints on standing. | I now faint when I stand up. |
| Supportive | Chinese | 现在一站起来就晕倒。 | 我现在一站起来就晕倒。 |
| Supportive | Japanese | 立ち上がった際に失神。 | 立ち上がったときに気を失いました。 |
| Diagnosis update | English | New temperature of 39.2 C. | I now have a temperature of 39.2 C. |
| Diagnosis update | Chinese | 体温新升至39.2℃。 | 我现在体温升到了39.2℃。 |
| Diagnosis update | Japanese | 新たに39.2℃の発熱。 | 新たに39.2℃の熱が出ました。 |

### V007

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No fever and significant history of smoking | I don't have a fever, and I've smoked a lot over the years. |
| Supportive | Chinese | 无发热，有较多吸烟史。 | 我没有发烧，以前烟抽得比较多。 |
| Supportive | Japanese | 発熱なし。相当量の喫煙歴あり。 | 熱はありません。たばこはかなりの量を吸ってきました。 |
| Urgency update | English | Moderate breathlessness at rest | I'm moderately short of breath even when I'm resting. |
| Urgency update | Chinese | 静息时中度气促。 | 我休息的时候也有中等程度的喘。 |
| Urgency update | Japanese | 安静時に中等度の息切れ。 | 安静にしていても中くらいの息切れがあります。 |
| Diagnosis update | English | He develops new unilateral calf swelling. | I've developed new swelling in one calf. |
| Diagnosis update | Chinese | 新出现单侧小腿肿胀。 | 我一侧的小腿新出现了肿胀。 |
| Diagnosis update | Japanese | 片側のふくらはぎに新たな腫脹。 | 片方のふくらはぎが新たに腫れてきました。 |

### V008

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No fever or haemoptysis | I don't have a fever, and I haven't coughed up any blood. |
| Supportive | Chinese | 无发热或咯血。 | 我没有发烧，也没有咳血。 |
| Supportive | Japanese | 発熱、喀血なし。 | 熱はなく、咳で血が出ることもありません。 |
| Urgency update | English | Cough interrupting sleep | The cough is interrupting my sleep. |
| Urgency update | Chinese | 咳嗽影响睡眠。 | 咳嗽影响了我的睡眠。 |
| Urgency update | Japanese | 咳で眠りが妨げられる。 | 咳で眠りが妨げられています。 |
| Diagnosis update | English | He develops small streaks of red in his sputum | I've started to get small streaks of red in my phlegm. |
| Diagnosis update | Chinese | 痰中出现少量红色血丝。 | 我的痰里出现了少量红色血丝。 |
| Diagnosis update | Japanese | 痰に少量の赤い筋が混じるようになった。 | 痰に少量の赤い筋が混じるようになりました。 |

### V009

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | Not drooling | I'm not drooling. |
| Supportive | Chinese | 无流涎。 | 我没有流口水。 |
| Supportive | Japanese | 流涎なし。 | よだれが垂れることはありません。 |
| Urgency update | English | Now cannot swallow water, feeling dehydrated | I now can't swallow water, and I feel dehydrated. |
| Urgency update | Chinese | 现在连水都咽不下，感觉脱水。 | 我现在连水都咽不下去，感觉自己脱水了。 |
| Urgency update | Japanese | 水も飲み込めず、脱水を自覚。 | 水も飲み込めず、脱水になっている感じがします。 |
| Diagnosis update | English | He develops stridor. | I've started making a harsh, high-pitched noise when I breathe. |
| Diagnosis update | Chinese | 出现喉鸣。 | 我喘气的时候喉咙里出现了尖锐的响声。 |
| Diagnosis update | Japanese | 吸気性喘鳴が出現。 | 息を吸うときにヒューヒューと高い音がするようになりました。 |

### V010

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No neurological deficit | I don't have any lasting weakness or numbness. |
| Supportive | Chinese | 无神经功能缺损。 | 我没有持续的无力或麻木。 |
| Supportive | Japanese | 神経脱落症状なし。 | 続くような脱力やしびれはありません。 |
| Urgency update | English | Her walking tolerance drops to under 20 metres because of the same leg symptoms. | Because of the same leg symptoms, I can now walk less than 20 metres. |
| Urgency update | Chinese | 因同样的腿部症状，现在走不到20米。 | 因为同样的腿部症状，我现在走不到20米。 |
| Urgency update | Japanese | 同じ下肢症状のため、20 mも歩けなくなった。 | 同じ脚の症状のため、20メートルも歩けなくなりました。 |
| Diagnosis update | English | She develops fever with new focal spinal tenderness. | I've developed a fever, and one spot on my spine has become tender. |
| Diagnosis update | Chinese | 出现发热，并伴新发脊柱局部压痛。 | 我发烧了，脊柱上还新出现了一处一按就疼的地方。 |
| Diagnosis update | Japanese | 発熱と新たな脊椎の限局性圧痛が出現。 | 熱が出て、背骨の一か所に押すと痛いところが新たに出てきました。 |

### V011

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No fever, haematuria, pain or acute retention | I don't have a fever, blood in my pee or pain, and I haven't suddenly been unable to pee. |
| Supportive | Chinese | 无发热、血尿、疼痛或急性尿潴留。 | 我没有发烧、尿血、疼痛，也没有突然尿不出来。 |
| Supportive | Japanese | 発熱、血尿、疼痛、急性尿閉なし。 | 熱、血尿、痛みはなく、急に尿が出なくなったこともありません。 |
| Urgency update | English | Unable to pass urine for the past 6 hours | I haven't been able to pee for the past 6 hours. |
| Urgency update | Chinese | 过去6小时无法排尿。 | 这6个小时我一直尿不出来。 |
| Urgency update | Japanese | ここ6時間、排尿できていない。 | ここ6時間、おしっこが出せていません。 |
| Diagnosis update | English | He has developed new visible blood in the urine. | I've started to see blood in my pee. |
| Diagnosis update | Chinese | 新出现肉眼血尿。 | 我的尿里新出现了肉眼能看见的血。 |
| Diagnosis update | Japanese | 新たに肉眼的血尿が出現。 | 新たに、目で見てわかる血尿が出ました。 |

### V012

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | Previous investigation for cardiac problems was reassuring | I was investigated for heart problems before, and the results were reassuring. |
| Supportive | Chinese | 以前做过心脏方面的检查，结果未见令人担忧的问题。 | 我以前做过心脏方面的检查，结果没有让人担心的问题。 |
| Supportive | Japanese | 以前の心臓の精査では懸念すべき所見なし。 | 以前に心臓の精密検査を受けましたが、心配な所見はありませんでした。 |
| Urgency update | English | Now unable to leave house for work | I'm now unable to leave the house to go to work. |
| Urgency update | Chinese | 现在已经无法出门上班。 | 我现在已经没办法出门上班了。 |
| Urgency update | Japanese | 出勤のために家を出られなくなった。 | 出勤のために家を出られなくなりました。 |
| Diagnosis update | English | She now reports active suicidal intent. | I now actively intend to take my own life. |
| Diagnosis update | Chinese | 现明确表示有自杀意图。 | 我现在明确有自杀的打算。 |
| Diagnosis update | Japanese | 現在、自殺する意思があると述べている。 | 今は、自殺しようという意思があります。 |

### V013

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No fever or rapidly spreading pain | I don't have a fever, and I don't have any pain that's spreading quickly. |
| Supportive | Chinese | 无发热，疼痛未迅速扩散。 | 我没有发烧，也没有迅速扩散的疼痛。 |
| Supportive | Japanese | 発熱や急速に広がる痛みなし。 | 熱はなく、急速に広がる痛みもありません。 |
| Urgency update | English | Itchy annular rash getting bigger despite cream use | The itchy ring-shaped rash is getting bigger even though I've been using a cream. |
| Urgency update | Chinese | 涂了药膏后，发痒的环形皮疹仍在扩大。 | 我涂了药膏，可是发痒的环形皮疹还在扩大。 |
| Urgency update | Japanese | 外用薬を塗っても、かゆみのある環状皮疹が拡大している。 | 塗り薬を塗っても、かゆみのある輪の形の発疹が広がっています。 |
| Diagnosis update | English | The affected area develops pain out of proportion to the visible rash. | The area has become painful, far more than you'd expect from how the rash looks. |
| Diagnosis update | Chinese | 患处疼痛程度明显超出皮疹外观看起来的程度。 | 我患处的疼痛明显超出了皮疹看上去该有的程度。 |
| Diagnosis update | Japanese | 皮疹の見た目に比べて著しく強い痛みが出現。 | 発疹の見た目に比べて、著しく強い痛みが出てきました。 |

### V014

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | Alert at present; omitted several insulin doses during a febrile illness | I'm alert at the moment. I missed several insulin doses while I was ill with a fever. |
| Supportive | Chinese | 目前意识清醒，发热期间漏用了数次胰岛素。 | 我现在意识清醒，发烧期间漏打了几次胰岛素。 |
| Supportive | Japanese | 現在は意識清明。発熱中にインスリンを数回打たなかった。 | 今は意識ははっきりしています。熱が出ている間、インスリンを数回打ちませんでした。 |
| Urgency update | English | Has not peed in last 8 hours | I haven't peed in the last 8 hours. |
| Urgency update | Chinese | 过去8小时未排尿。 | 我这8个小时没有尿过。 |
| Urgency update | Japanese | ここ8時間、排尿がない。 | ここ8時間、おしっこが出ていません。 |
| Diagnosis update | English | New central crushing chest pain at rest. | I have a new crushing pain in the centre of my chest while I'm resting. |
| Diagnosis update | Chinese | 静息时新出现胸部中央压榨性疼痛。 | 我休息的时候新出现了胸口正中的压榨样疼痛。 |
| Diagnosis update | Japanese | 安静時に前胸部中央の押しつぶされるような痛みが新たに出現。 | 安静にしているときに、胸の真ん中に押しつぶされるような痛みが新たに出てきました。 |

### V015

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No testicular pain or systemic fever | I don't have any pain in my testicles, and I don't have a fever. |
| Supportive | Chinese | 无睾丸痛或发热。 | 我没有睾丸痛，也没有发烧。 |
| Supportive | Japanese | 精巣痛や発熱なし。 | 睾丸の痛みや熱はありません。 |
| Urgency update | English | Dysuria significant enough to not pee | It stings so much to pee that I'm not peeing. |
| Urgency update | Chinese | 排尿太痛，以至于没有排尿。 | 我小便时疼得太厉害，所以一直没有小便。 |
| Urgency update | Japanese | 排尿時の痛みが強く、排尿していない。 | おしっこのときの痛みが強くて、おしっこをしていません。 |
| Diagnosis update | English | He develops a new tender, swollen epididymis. | I've developed a new tender swelling at the back of one testicle. |
| Diagnosis update | Chinese | 新出现附睾肿胀和压痛。 | 我睾丸后面新出现了肿胀，一按就疼。 |
| Diagnosis update | Japanese | 精巣上体の腫脹と圧痛が新たに出現。 | 睾丸の後ろ側が新たに腫れて、押すと痛みます。 |

### V016

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No rectal bleeding, fever or weight loss | I haven't had any bleeding from my back passage, fever or weight loss. |
| Supportive | Chinese | 无直肠出血、发热或体重下降。 | 我没有肛门出血、发烧或体重下降。 |
| Supportive | Japanese | 直腸出血、発熱、体重減少なし。 | お尻からの出血、熱、体重減少はありません。 |
| Urgency update | English | Constipation ongoing for four days, causing moderate pain but no other worsening symptos | I've been constipated for four days, which is causing moderate pain, but none of my other symptoms have got worse. |
| Urgency update | Chinese | 便秘已4天，伴中度疼痛，其他症状没有加重。 | 我已经便秘4天了，有中等程度的疼痛，其他症状没有加重。 |
| Urgency update | Japanese | 便秘が4日続き、中等度の痛みがあるが、ほかに悪化した症状はない。 | 便秘が4日続いていて中くらいの痛みがありますが、ほかに悪くなった症状はありません。 |
| Diagnosis update | English | She now reports persistent unexplained weight loss. | I've now been losing weight persistently, and I can't explain why. |
| Diagnosis update | Chinese | 现报告体重持续下降，原因不明。 | 我现在体重持续下降，找不到原因。 |
| Diagnosis update | Japanese | 原因不明の体重減少が続いているとのこと。 | 原因のわからない体重減少が続いています。 |

### V017

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | Recent cold | I've recently had a cold. |
| Supportive | Chinese | 近期感冒。 | 我最近感冒过。 |
| Supportive | Japanese | 最近かぜをひいた。 | 最近かぜをひきました。 |
| Urgency update | English | Significant thick yellow pus, accumulating after wiping but no change in vision | There's a lot of thick yellow pus, and it builds up again after I wipe it away, but my vision hasn't changed. |
| Urgency update | Chinese | 有大量黏稠脓性黄色分泌物，擦掉后又积聚，视力无变化。 | 我眼睛有很多黏稠的黄色脓性分泌物，擦掉后又会积起来，视力没有变化。 |
| Urgency update | Japanese | 粘り気の強い黄色の膿性眼脂が多く、拭いてもまたたまる。見え方に変化なし。 | 粘り気の強い黄色い膿のような目やにが多く、拭いてもまたたまります。見え方に変化はありません。 |
| Diagnosis update | English | She develops a unilateral vesicular rash over the nose and forehead. | I've developed a blistering rash on one side of my nose and forehead. |
| Diagnosis update | Chinese | 鼻部和前额单侧出现水疱性皮疹。 | 我鼻子和额头的一侧出现了水疱样的皮疹。 |
| Diagnosis update | Japanese | 鼻と額の片側に水疱性皮疹が出現。 | 鼻と額の片側に水ぶくれのような発疹が出ました。 |

### V018

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No fever or immunosuppression | I don't have a fever, and my immune system isn't weakened. |
| Supportive | Chinese | 无发热，无免疫抑制。 | 我没有发烧，免疫力也没有受到抑制。 |
| Supportive | Japanese | 発熱や免疫抑制なし。 | 熱はなく、免疫が抑えられている状態でもありません。 |
| Urgency update | English | He develops unilateral facial weakness. | One side of my face has become weak. |
| Urgency update | Chinese | 出现单侧面部无力。 | 我一侧的脸出现了无力。 |
| Urgency update | Japanese | 片側の顔面筋力低下が出現。 | 顔の片側に力が入らなくなりました。 |
| Diagnosis update | English | Itchiness has settled, hearing still muffled | The itchiness has settled, but my hearing is still muffled. |
| Diagnosis update | Chinese | 耳痒已缓解，但听声音仍发闷。 | 我的耳朵已经不痒了，但听声音还是发闷。 |
| Diagnosis update | Japanese | かゆみは治まったが、音はまだこもって聞こえる。 | かゆみは治まりましたが、音はまだこもって聞こえます。 |

### V019

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | She has had similar episodes of knee pain that resolved without treatment. | I've had similar episodes of knee pain before, and they got better without treatment. |
| Supportive | Chinese | 以前也出现过类似膝痛，未经治疗自行缓解。 | 我以前也有过类似的膝盖疼，没有治疗就自己好了。 |
| Supportive | Japanese | 以前にも同様の膝痛があり、治療せずに軽快した。 | 以前にも同じような膝の痛みがあり、治療せずに良くなりました。 |
| Urgency update | English | She becomes unable to bear weight on the affected leg. | I can no longer put weight on that leg. |
| Urgency update | Chinese | 患侧腿已无法负重。 | 我这条腿已经没办法承重了。 |
| Urgency update | Japanese | 患側の脚に体重をかけられなくなった。 | 痛いほうの脚に体重をかけられなくなりました。 |
| Diagnosis update | English | Her knee suddenly becomes very hot and red overnight. | My knee suddenly became very hot and red overnight. |
| Diagnosis update | Chinese | 一夜之间膝关节突然明显发红、发热。 | 我的膝盖一夜之间突然明显发红、发热。 |
| Diagnosis update | Japanese | 一晩で膝が急に赤くなり、強い熱感が出た。 | 一晩で膝が急に赤くなり、強い熱を持ちました。 |

### V020

| Update | Language | Note in the sheet | Patient's words |
|---|---|---|---|
| Supportive | English | No persistent swelling or neurological changes | I don't have any lasting swelling, or any changes in feeling or strength. |
| Supportive | Chinese | 无持续肿胀或神经系统变化。 | 我没有持续的肿胀，感觉和力气也没有变化。 |
| Supportive | Japanese | 持続する腫脹や神経症状なし。 | 続くような腫れや、感覚や力の入り方の変化はありません。 |
| Urgency update | English | The cramps recur at rest and interrupt sleep | The cramps come back when I'm resting, and they interrupt my sleep. |
| Urgency update | Chinese | 休息时也会抽筋，影响睡眠。 | 我休息的时候也会抽筋，影响睡眠。 |
| Urgency update | Japanese | 安静時にも脚がつり、眠りが妨げられる。 | 安静にしているときにも脚がつり、眠りが妨げられます。 |
| Diagnosis update | English | His urine becomes dark brown after strenuous exercise. | My pee has turned dark brown after strenuous exercise. |
| Diagnosis update | Chinese | 剧烈运动后尿液呈深褐色。 | 我剧烈运动后尿变成了深褐色。 |
| Diagnosis update | Japanese | 激しい運動の後、尿が濃い茶色になった。 | 激しい運動の後、尿が濃い茶色になりました。 |
