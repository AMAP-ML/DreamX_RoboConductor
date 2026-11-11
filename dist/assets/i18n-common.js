// Interface translations; task names retain their original English labels.
(window.ShowcaseTranslations ||= []).push({
  "strings": {
    "Future Work": "未来工作",
    "Last updated:": "更新于：",
    "Episodes": "试验",
    "Episode": "试验",
    "Success rate": "成功率",
    "Control time": "执行时间",
    "Scoring": "评分方式",
    "Official evaluator": "官方评测器",
    "Official task evaluator": "官方任务评测器",
    "Pick up the blue pen on the box and insert it into the pen holder on the right.": "抓取盒子上蓝色的笔插入右侧笔筒中。",
    "Pick up the phone on the box and place it on the phone stand on the right.": "抓取盒子上的手机放在右侧手机架上。",
    "Videos": "视频",
    "Method": "方法",
    "Results": "结果",
    "Case study": "案例分析",
    "Case Study": "案例分析",
    "Resources": "资源",
    "Experiments": "实验档案",
    "Simulation": "仿真",
    "Real world": "真机",
    "Real-world": "真机",
    "Real World": "真机",
    "Success": "成功",
    "Failure": "失败",
    "success": "成功",
    "failure": "失败",
    "SUCCESS": "成功",
    "FAILURE": "失败",
    "Turn": "轮次",
    "Scene": "场景",
    "Task": "任务",
    "Tasks": "任务",
    "Trials": "试验",
    "Trial": "试验",
    "Replay": "回放",
    "Play": "播放",
    "Pause": "暂停",
    "Play episode": "播放回合",
    "Pause episode": "暂停回合",
    "Previous turn": "上一轮",
    "Next turn": "下一轮",
    "Head": "头部",
    "Left wrist": "左腕",
    "Right wrist": "右腕",
    "Head camera": "头部相机",
    "Left wrist camera": "左腕相机",
    "Right wrist camera": "右腕相机",
    "External camera": "外部相机",
    "Close": "关闭",
    "Open": "打开",
    "All": "全部",
    "All tasks": "全部任务",
    "All outcomes": "全部结果",
    "All platforms": "全部平台",
    "Loading…": "加载中…",
    "Loading...": "加载中…",
    "Search": "搜索",
    "Reset": "重置",
    "Filter": "筛选",
    "Outcome": "结果",
    "Platform": "平台",
    "Observations": "观测",
    "Turns": "轮次",
    "Duration": "时长",
    "Seed": "随机种子",
    "View all": "查看全部",
    "View archive": "查看归档",
    "Open full episode": "打开完整回合",
    "Full episode": "完整回合",
    "Back to home": "返回首页",
    "Home": "首页",
    "Previous": "上一项",
    "Next": "下一项",
    "Camera": "相机",
    "Camera views": "相机视角",
    "Head camera view": "头部相机视角",
    "Left wrist camera view": "左腕相机视角",
    "Right wrist camera view": "右腕相机视角",
    "Select head camera": "选择头部相机",
    "Select left wrist camera": "选择左腕相机",
    "Select right wrist camera": "选择右腕相机",
    "Introduction": "项目介绍"
  },
  "patterns": [
    {
      "source": "^(\\d+) of (\\d+)$",
      "replacement": "$1 / $2"
    },
    {
      "source": "\\bEP\\s+(\\d+)\\b",
      "replacement": "试验 $1",
      "flags": "g"
    },
    {
      "source": "\\bScene\\s+(\\d+)\\b",
      "replacement": "场景 $1",
      "flags": "g"
    },
    {
      "source": "\\bscene\\s+(\\d+)\\b",
      "replacement": "场景 $1",
      "flags": "g"
    },
    {
      "source": "\\bTurn\\s+(\\d+)\\b",
      "replacement": "第 $1 轮",
      "flags": "g"
    },
    {
      "source": "\\bturn\\s+(\\d+)\\b",
      "replacement": "第 $1 轮",
      "flags": "g"
    },
    {
      "source": "\\btrial\\s+(\\d+)\\b",
      "replacement": "第 $1 次试验",
      "flags": "g"
    },
    {
      "source": "\\bTrial\\s+(\\d+)\\b",
      "replacement": "第 $1 次试验",
      "flags": "g"
    },
    {
      "source": "\\bseed\\s*:?\\s*(\\d+)\\b",
      "replacement": "随机种子 $1",
      "flags": "g"
    },
    {
      "source": "\\bSeed\\s*:?\\s*(\\d+)\\b",
      "replacement": "随机种子 $1",
      "flags": "g"
    },
    {
      "source": "\\b(\\d+) turns\\b",
      "replacement": "$1 轮",
      "flags": "g"
    },
    {
      "source": "\\b(\\d+) observations\\b",
      "replacement": "$1 次观测",
      "flags": "g"
    },
    {
      "source": "\\b(\\d+) trials\\b",
      "replacement": "$1 次试验",
      "flags": "g"
    },
    {
      "source": "\\b(\\d+) tasks\\b",
      "replacement": "$1 项任务",
      "flags": "g"
    },
    {
      "source": "\\b(\\d+) successes\\b",
      "replacement": "$1 次成功",
      "flags": "g"
    },
    {
      "source": "\\b(\\d+) failures\\b",
      "replacement": "$1 次失败",
      "flags": "g"
    },
    {
      "source": "\\b(\\d+(?:\\.\\d+)?) seconds\\b",
      "replacement": "$1 秒",
      "flags": "g"
    },
    {
      "source": "\\b(\\d+(?:\\.\\d+)?) minutes\\b",
      "replacement": "$1 分钟",
      "flags": "g"
    },
    {
      "source": "\\bHead-camera observation at (?:turn (\\d+)|第 (\\d+) 轮)",
      "replacement": "头部相机观测 · 第 $1$2 轮",
      "flags": "g"
    },
    {
      "source": "\\bLeft-wrist-camera observation at (?:turn (\\d+)|第 (\\d+) 轮)",
      "replacement": "左腕相机观测 · 第 $1$2 轮",
      "flags": "g"
    },
    {
      "source": "\\bTask SUCCESS\\b",
      "replacement": "任务成功",
      "flags": "g"
    },
    {
      "source": "\\bTask FAILURE\\b",
      "replacement": "任务失败",
      "flags": "g"
    },
    {
      "source": "\\bsuccess in (\\d+) 轮",
      "replacement": "成功，共 $1 轮",
      "flags": "g"
    },
    {
      "source": "\\bfailure in (\\d+) 轮",
      "replacement": "失败，共 $1 轮",
      "flags": "g"
    },
    {
      "source": "\\bSuccess\\b",
      "replacement": "成功",
      "flags": "g"
    },
    {
      "source": "\\bFailure\\b",
      "replacement": "失败",
      "flags": "g"
    },
    {
      "source": "\\bsuccess\\b",
      "replacement": "成功",
      "flags": "g"
    },
    {
      "source": "\\bfailure\\b",
      "replacement": "失败",
      "flags": "g"
    },
    {
      "source": "\\. Open full episode\\.",
      "replacement": "。打开完整回合。",
      "flags": "g"
    },
    {
      "source": ": open full episode$",
      "replacement": "：打开完整回合"
    }
  ]
});
