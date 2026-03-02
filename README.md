# pkit

## `uvrun`
uvで管理しているスクリプトの実行ヘルパー。

```shell
# 実行するスクリプトのプロジェクトディレクトリを指定して実行
uvx --from git+https://github.com/cosomil/pkit@uvrun uvrun {path_to_project_dir}
# 過去に実行したことのあるプロジェクトを選択して実行
uvx --from git+https://github.com/cosomil/pkit@main uvrun
```
