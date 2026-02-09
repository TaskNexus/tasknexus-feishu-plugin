# TaskNexus Feishu Plugin

飞书 (Feishu) channel plugin for TaskNexus.

## Installation

```bash
pip install git+https://github.com/TaskNexus/tasknexus-feishu-plugin.git
```

## Configuration

Set environment variables:

```bash
export FEISHU_APP_ID=cli_xxxxx
export FEISHU_APP_SECRET=xxxxx
```

Or use the `TASKNEXUS_PLUGIN_FEISHU_*` prefix:

```bash
export TASKNEXUS_PLUGIN_FEISHU_APP_ID=cli_xxxxx
export TASKNEXUS_PLUGIN_FEISHU_APP_SECRET=xxxxx
```

## Usage

```bash
python manage.py channel_bot --channel feishu
```

## Feishu Configuration

1. Create an app at [Feishu Open Platform](https://open.feishu.cn)
2. Get App ID and App Secret from credentials page
3. Enable required permissions:
   - `im:message`
   - `im:message.p2p_msg:readonly`
   - `im:message.group_at_msg:readonly`
   - `im:message:send_as_bot`
4. Configure event subscription (use **Long Connection** mode):
   - `im.message.receive_v1`
   - `im.message.message_read_v1`

## License

MIT
