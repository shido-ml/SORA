# 直るナビの日次記事公開

公開先は既存の `https://sora-navi-jp.com/`、GitHub Pages の `shido-ml/SORA` の `main` ルートです。定期実行設定はこのリポジトリにありません。外部の定期タスクを使う場合、実行時刻の提案は日本時間の毎日 09:00 です。重複するスケジュールを新設しないでください。

1. `main` の最新状態と当日（日本時間）の公開済み記事を確認します。既存の `data/search-index.json`、公開記事、当日の Git 履歴を参照し、その日の残枠を計算します。すでに30本なら終了します。
2. 他の記事と異なる検索意図を持つ困りごとだけを選びます。製品・サービス提供者の一次資料を実際に読み、事実、操作順、データ消去の注意、相談先を確認します。体験談や検証していない仕様を書きません。
3. `data/daily/YYYY-MM-DD.json` に、既存の `data/new-articles-plan.json` と同じ項目に加え、個別の `diagnosis`（100字以上）、`caution`（70字以上）、`fact_check`（確認した一次資料と照合内容、40字以上）を記します。`related_existing` は既存または同時公開する記事の正規パスです。同日のファイルには公開済みも含めて最大30本を記載します。
4. `python -m pip install -r requirements.txt` の後、`python scripts/publish_daily_batch.py --date YYYY-MM-DD --check` を実行します。重複 URL、類似タイトル、リンク、正規 URL、日付、件数を確認し、問題がなければ `--check` なしで生成します。
5. `python scripts/verify_site.py` と `git diff --check` を実行します。記事ごとに内容と一次資料を再確認します。`main` の更新があれば取り込み、当日の追加数を再計算してから公開します。
6. 既存の `main` 公開経路で反映した後、記事 URL と `https://sora-navi-jp.com/sitemap.xml` の HTTP 応答、XML の構文、記事の `<loc>` と `<lastmod>` を確認します。二度目の実行では `files_to_write=0` になることを確認します。

`publish_daily_batch.py` は記事を自動で発想・執筆しません。実行時に一次資料の可用性を判断する機能もないため、執筆・編集時の確認が必要です。サイトマップの既存記事の `lastmod` は維持し、新記事と実際に更新した一覧ページの日付だけを更新します。
