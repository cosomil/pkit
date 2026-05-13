# pkit

## `enforce_uv_policy`
uvのセキュリティ設定ポリシーを設定する。
サプライチェーン攻撃に対する防御に関する設定などを定める。

```shell
uvx --from git+https://github.com/cosomil/pkit@main enforce_uv_policy
```

## `uvrun`
uvで管理しているスクリプトの実行ヘルパー。

```shell
# 実行するスクリプトのプロジェクトディレクトリを指定して実行
uvx --from git+https://github.com/cosomil/pkit@main uvrun {path_to_project_dir}
# 過去に実行したことのあるプロジェクトを選択して実行
uvx --from git+https://github.com/cosomil/pkit@main uvrun
```
