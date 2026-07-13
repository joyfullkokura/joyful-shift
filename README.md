# Joyful-Shift

> **現場の課題を見つけ、利用者の意見を聞きながら改善し続ける。**  
> ジョイフル店長のシフト作成時間を90%以上削減することを達成した、クラウド型シフト管理システムです。

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-WebApp-red)
![Flask](https://img.shields.io/badge/Flask-Backend-lightgrey)
![Status](https://img.shields.io/badge/Status-Beta-success)
![License](https://img.shields.io/badge/License-MIT-green)

---

#  プロジェクト概要

Joyful-Shiftは、ファミリーレストラン「ジョイフル」の複雑な勤務体系に特化したシフト管理システムです。

アルバイトとして働く中で、店長が毎月何時間もシフト作成に追われ、本来注力すべき

- 接客・従業員教育
- 店舗改善
- 売上分析

に十分な時間を割けていない現状を目の当たりにしました。

「この時間をもっと価値のある仕事に使ってほしい。」

そんな思いから、実際に店長へ試作版を使っていただき、フィードバックを受けながら改善を繰り返してきました。

現在はβ版を運用中で、多店舗対応・SaaS化を進めています。

---

# 解決する課題

## 店長の負担

- シフト作成に毎月数時間～十数時間必要
- 人件費のロス
- 休憩時間の計算
- 社員168時間管理
- 社員の月間労働目標の管理が困難であり、未達による固定費の無駄
- 労働法に基づく休憩時間の算出
---

## スタッフの負担

- 店舗でしか休み希望を提出できない
- シフト完成まで時間がかかる
- 入力ミス・希望漏れ
- 不公平なシフト

---

##  経営課題

- 人件費の最適化
- 労働基準法への対応
- 欠員把握
- 人時管理

---

#  主な機能

## シフト自動生成

- 希望休を考慮
- 希望勤務日数を考慮
- スキルを考慮
- 社員の月間労働目標管理
- 連勤回避
- 公平性を考慮した割り当て

---

## スマホから休み希望提出

スタッフはスマートフォンからいつでも希望休を入力できます。

入力内容はリアルタイムで店長画面へ反映されます。

---

## 人件費・人時計算

勤務時間を変更すると、

- 概算総人時

をリアルタイムで表示します。

---

##  Excel自動出力

ジョイフルの運用に合わせたExcelをワンクリックで生成。

店長は最終確認・微調整のみで完成できます。

一人一人の実働時間の合計や週希望日数に対する充足率などを動的に表示しているため、変動費の計算や全員にとって満足度の高いシフトかどうかが一目でわかります。

---

##  LINE通知

シフト公開時にスタッフへLINE通知を送信できます。

---

#  技術スタック

|分類|技術|
|---|---|
|Language|Python|
|Framework|Streamlit・Flask|
|Database|Google Sheets API|
|Excel|xlsxwriter|
|Notification|LINE Messaging API|
|Version Control|Git・GitHub|

---

#  システム画面

## スマホから休み希望入力（実際に従業員の皆様に説明するときに使った画像です）

<img width="1251" height="1087" alt="messageImage_1783587956821" src="https://github.com/user-attachments/assets/70efc645-b7a1-43eb-b262-9590b678cee2" />




<img width="1051" height="1075" alt="messageImage_1783587976769" src="https://github.com/user-attachments/assets/d2a69e46-0aa3-49d1-9914-7cb785d3ce6f" />



---

## シフト生成画面

<img width="1912" height="1005" alt="messageImage_1782375206314" src="https://github.com/user-attachments/assets/6ea1ea5b-f500-48a8-b669-f2d6cae80da4" />



<img width="955" height="528" alt="スクリーンショット 2026-07-05 033926" src="https://github.com/user-attachments/assets/10f3bab7-0df9-48a2-92a1-eb6f75cc0ecc" />



<img width="688" height="403" alt="スクリーンショット 2026-07-03 162656" src="https://github.com/user-attachments/assets/8d58d35e-e7ef-41f5-88d7-1aad2d2e46bc" />



<img width="959" height="536" alt="スクリーンショット 2026-07-03 162906" src="https://github.com/user-attachments/assets/e0a3735c-f889-40fd-9b0e-22745a9752f7" />




<img width="959" height="537" alt="スクリーンショット 2026-07-05 034033" src="https://github.com/user-attachments/assets/b45f78ae-039f-43b5-b14f-e01217c09ead" />



<img width="959" height="527" alt="スクリーンショット 2026-07-14 013213" src="https://github.com/user-attachments/assets/f92d6f22-2f46-4d71-85ea-3879be8719b6" />






---

## Excel出力

<img width="4623" height="2863" alt="messageImage_1782374582541" src="https://github.com/user-attachments/assets/a96c9cb9-bdeb-44e8-99a6-18d492d003a6" />




<img width="717" height="403" alt="スクリーンショット 2026-07-03 164156" src="https://github.com/user-attachments/assets/1fe63e4c-6149-4dd9-aeae-21e828f1647c" />


---

## 管理画面

<img width="956" height="532" alt="スクリーンショット 2026-07-14 013610" src="https://github.com/user-attachments/assets/27752138-3791-4607-ad5b-e52fa5949acd" />


<img width="957" height="529" alt="スクリーンショット 2026-07-14 021416" src="https://github.com/user-attachments/assets/d17640b2-c479-4e9b-9477-77b557887e8e" />



---

#  システム構成

```text
スタッフ
      │
      ▼
スマホから希望休入力
      │
      ▼
Google Sheets
      │
      ▼
Pythonシフト生成アルゴリズム
      │
      ▼
Streamlit
      │
      ├── Excel出力
      ├── LINE通知
      └── 人件費・人時計算
```

---

#  今後の展望

現在はジョイフル1店舗向けに開発しています。

今後は

- 多店舗対応
- PostgreSQLへの移行
- SaaS化
- サブスクリプション提供
- 他飲食チェーンへの展開
- AIによる最適シフト生成精度向上

を目指しています。

---

# さいごに

私は、アルバイトとして働く中で、店長が毎月何時間もシフト作成に追われている姿を見て、「この負担は技術で解決できるはずだ」と考えたことが開発のきっかけです。
そのため、実際に店長へ試作版を使っていただき、現場の声を反映しながら改善を重ねてきました。
私が目指しているのは、「現場で安心して使い続けてもらえるシステム」を作ることです。
利用者から「助かった」「使いやすい」と言っていただける瞬間が、開発を続ける一番の原動力です。
これからも現場の課題を丁寧に拾い上げ、技術を通して働く人を支えられるシステムを開発していきたいと考えています。

---


