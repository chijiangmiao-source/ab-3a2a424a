// SiO2 多晶型示例：六个候选相在八个诊断反射上的预期出现关系。
// 其中 101 与 102 的出现关系与代价完全相同，用于演示"可选"角色（二者可互换）。
export const SAMPLE = {
  phases: ["α-石英", "β-石英", "方石英", "鳞石英", "柯石英", "斯石英"],
  reflections: [
    { id: "100", cost: 2 },
    { id: "101", cost: 3 },
    { id: "110", cost: 2 },
    { id: "102", cost: 3 },
    { id: "200", cost: 5 },
    { id: "211", cost: 1 },
    { id: "003", cost: 6 },
    { id: "301", cost: 8 },
  ],
  // occurrence[相][反射] = 是否预期出现
  occurrence: {
    "α-石英": { "100": true, "101": true, "110": false, "102": true, "200": false, "211": false, "003": false, "301": true },
    "β-石英": { "100": true, "101": false, "110": true, "102": false, "200": false, "211": false, "003": true, "301": false },
    "方石英": { "100": false, "101": true, "110": false, "102": true, "200": true, "211": false, "003": true, "301": false },
    "鳞石英": { "100": false, "101": false, "110": true, "102": false, "200": true, "211": true, "003": false, "301": true },
    "柯石英": { "100": true, "101": false, "110": false, "102": false, "200": true, "211": false, "003": false, "301": true },
    "斯石英": { "100": false, "101": false, "110": false, "102": false, "200": false, "211": true, "003": true, "301": false },
  },
};
