const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const appPath = path.join(__dirname, "app.js");
const appCode = `${fs.readFileSync(appPath, "utf8")}\nthis.__buildTasks = buildTasks; this.__state = state; this.__addToBasket = addToBasket; this.__orderedBasketItems = orderedBasketItems; this.__collapseTask = collapseTask; this.__collapseAllTasks = collapseAllTasks;`;

const fakeElement = {
  value: "",
  textContent: "",
  innerHTML: "",
  hidden: false,
  classList: { add() {}, remove() {}, toggle() {} },
  addEventListener() {},
};

const context = {
  console,
  setTimeout,
  clearTimeout,
  document: {
    documentElement: { style: { setProperty() {} } },
    querySelector: () => fakeElement,
    querySelectorAll: () => [],
  },
};

vm.createContext(context);
vm.runInContext(appCode, context);

const sample = `今儿咱说个事儿
说出来丢人
想起来又挺解气
上个月在布拉格看一个东亚文化展
展厅正中挂着一幅两米多高的《水浒人物长卷》
水墨压下来
每一笔都像藏着股杀气
旁边一个研究中国古典小说很多年的老教授
听说我是中国人
先指着林冲问
风雪山神庙那段
林冲杀陆谦之前
为什么偏偏先看一眼酒葫芦
我当场愣住
我知道林冲
知道风雪山神庙
可从没想过他拔刀前为什么还要看那一眼
他又指着鲁智深
三拳打死镇关西
按你们古代的规矩杀人偿命
他怎么还能大摇大摆走出城
接着又问武松
十八碗酒下肚
人都醉成那样了
为什么还能看清老虎那三招
茶都凉了
一个外国人问我中国英雄的命运
我一个也答不上来
老教授见我不说话
指着画说
你看林冲眉头的雪
鲁智深拳头的茧
宋江腰间的刀`;

const tasks = context.__buildTasks(sample);
const queries = tasks.map((task) => task.query);

assert.strictEqual(tasks.length, sample.split("\n").length, "应该每一行生成一个搜索任务");
[
  "说话 口播 人物",
  "真人 尴尬 影视剧照",
  "真人 解气 影视剧照",
  "布拉格 东亚文化展",
  "展厅 水浒人物长卷",
  "水墨 宣纸",
  "毛笔 写字 杀气",
  "老教授",
  "侧耳 倾听",
  "指着林冲",
  "雪山神庙",
  "林冲 陆谦",
  "酒葫芦",
  "真人 语塞 影视剧照",
  "古代人物 拔刀",
  "鲁智深",
  "三拳打死镇关西",
  "中国古代 人物",
  "古代城门 出城",
  "武松",
  "古代喝酒",
  "真人 喝醉 影视剧照",
  "老虎",
  "一杯茶",
  "外国人 人物",
  "指着一幅画",
  "林冲 雪",
  "拳头上茧",
  "宋江带刀",
].forEach((expected) => assert(queries.includes(expected), `缺少关键词：${expected}`));

context.__state.tasks = [
  {
    id: "S01",
    order: 1,
    segment: "第一段",
    query: "测试",
    expanded: true,
    items: [
      { id: "same-id", title: "第一张", source: "测试", thumb: "https://example.com/1-thumb.jpg", image: "https://example.com/1.jpg" },
      { id: "same-id", title: "第二张", source: "测试", thumb: "https://example.com/2-thumb.jpg", image: "https://example.com/2.jpg" },
    ],
  },
];
context.__state.basket = [];
context.__state.pickSeq = 0;
context.__addToBasket(0, 0);
context.__addToBasket(0, 1);

assert.strictEqual(context.__state.basket.length, 2, "同一段应该可以连续添加两张不同图片");
const orderedLabels = Array.from(context.__orderedBasketItems().map((item) => `${item.taskId}-${item.slot}`));
assert.deepStrictEqual(
  orderedLabels,
  ["S01-1", "S01-2"],
  "素材篮应保留段内选择顺序",
);

context.__collapseTask(0);
assert.strictEqual(context.__state.tasks[0].expanded, false, "收起本段应该关闭当前段落");
context.__state.tasks.push({ id: "S02", order: 2, segment: "第二段", query: "测试二", expanded: true, items: [] });
context.__collapseAllTasks();
assert(context.__state.tasks.every((task) => task.expanded === false), "全部收起应该关闭所有段落");

console.log(`关键词自检通过：${tasks.length} 行，${new Set(queries).size} 个首选搜索词。`);
