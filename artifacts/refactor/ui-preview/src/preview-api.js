/** 业务页面预览专用合成接口，替换 fetch 必须早于业务模块导入，绝不转发真实请求。 */
export function installPreviewApi() {
  const favorites = new Set([2]);
  const data = [
    [
      "计算机网络 第 7 版 · 少量笔记",
      18,
      59,
      "books",
      "book0",
      "第 7 版",
      "小林同学",
    ],
    [
      "Python 程序设计，入门课教材",
      15,
      49,
      "books",
      "book1",
      "版次见详情",
      "阿晴",
    ],
    [
      "实木折叠小凳，宿舍收纳不占地",
      29,
      69,
      "living",
      "item0",
      "九成新",
      "柚子",
    ],
    [
      "暖光台灯 · 陪你读完下一本书",
      25,
      79,
      "living",
      "item1",
      "九成新",
      "小满",
    ],
    [
      "数据结构（C 语言版），无缺页",
      16,
      45,
      "books",
      "book2",
      "C 语言版",
      "阿哲",
    ],
    [
      "羽毛球拍一支，周末一起上场",
      38,
      128,
      "sports",
      "item2",
      "正常使用痕迹",
      "橙子",
    ],
    ["高等数学上册，送给需要的同学", 0, 49, "books", "book3", "上册", "阿禾"],
    [
      "大学英语综合教程，有少量笔记",
      12,
      42,
      "books",
      "book4",
      "综合教程",
      "木木",
    ],
    [
      "操作系统教材，继续陪你学习",
      18,
      58,
      "books",
      "book5",
      "版次见详情",
      "陈同学",
    ],
  ].map((item, index) => ({
    id: index + 1,
    seller_id: 100 + index,
    title: item[0],
    price: item[1] * 100,
    original_price: item[2] * 100,
    category: item[3],
    edition: item[3] === "books" ? item[5] : "",
    condition: item[3] === "books" ? "有少量笔记" : item[5],
    nickname: item[6],
    photos: [{ url: "/assets/" + item[4] + ".svg" }],
    status: "available",
    simulation: true,
    region: index % 2 ? "教学楼 A 栋" : "图书馆门口",
    delivery: index % 2 ? "pickup" : "both",
    delivery_fee: index % 2 ? 0 : 200,
  }));
  // 演示用户和记录全为合成内容，不读取真实资料或数据库。
  const now = Math.floor(Date.now() / 1000);
  const me = {
    id: 7,
    nickname: "预览同学",
    role: "user",
    score: 100,
    college: "计算机工程学院",
    major: "软件工程",
    degree_level: "bachelor",
    study_status: "studying",
    profile_version: 1,
    bio: "这是一份演示资料，用来预览个人中心。",
    avatar_url: "",
    star_label: "校园同学",
  };
  data[data.length - 1].seller_id = 7;
  data[data.length - 1].nickname = me.nickname;
  data.forEach((p) => {
    p.description =
      "【演示商品】" +
      p.title +
      "。物品状态、版次及交付地点均为合成内容，真实发布与交易需要另一台电脑联调。";
    p.created = now - p.id * 600;
  });
  const posts = [
    {
      id: 201,
      user_id: 100,
      nickname: "小林同学",
      topic: "交流",
      body: "图书馆三楼的阅读角，安静又舒服\n最近发现了一处适合自习的位置，窗边光线很好。大家还有推荐的学习地点吗？",
      created: now - 3600,
      replies: 2,
    },
    {
      id: 202,
      user_id: 101,
      nickname: "阿晴",
      topic: "毕业季",
      body: "毕业季整理清单，给闲置找个新主人\n整理书架时发现很多好书，希望下一位同学能继续用上。",
      created: now - 7200,
      replies: 1,
    },
    {
      id: 203,
      user_id: 7,
      nickname: me.nickname,
      topic: "交换人生",
      body: "用一本喜欢的书，交换一个新故事\n想换一本校园生活或旅行题材的书，当面交流也欢迎。",
      created: now - 10800,
      replies: 1,
    },
    {
      id: 204,
      user_id: 102,
      nickname: "柚子",
      topic: "代拿快递",
      body: "今天傍晚顺路去快递站\n有需要的同学可以在这里交流取件时间，注意保护个人信息。",
      created: now - 14400,
      replies: 0,
    },
  ];
  const comments = [
    {
      id: 301,
      post_id: 201,
      user_id: 7,
      nickname: me.nickname,
      parent_id: 0,
      body: "我也喜欢这个位置，下午光线很好。",
      created: now - 1800,
    },
    {
      id: 302,
      post_id: 201,
      user_id: 101,
      nickname: "阿晴",
      parent_id: 301,
      body: "谢谢分享，明天去看看。",
      created: now - 1200,
    },
  ];
  const wants = [
    {
      id: 401,
      user_id: 101,
      nickname: "阿晴",
      keyword: "求购数据结构教材",
      description: "希望是 C 语言版，没有缺页；可在图书馆门口自提。",
      budget: 2000,
      created: now - 5400,
      status: "open",
      matches: [data[4]],
    },
    {
      id: 402,
      user_id: 7,
      nickname: me.nickname,
      keyword: "想收一盏宿舍台灯",
      description: "亮度可调，正常使用即可。",
      budget: 3000,
      created: now - 7200,
      status: "open",
      matches: [data[3]],
    },
  ];
  const rooms = [
    {
      id: 9,
      name: "小林同学",
      peer_name: "小林同学",
      peer_id: 100,
      kind: "private",
      role: "member",
      last_body: "明天下午图书馆门口见，记得核对版次。",
      unread: 1,
      blocked: false,
      muted: false,
    },
    {
      id: 11,
      name: "华立校园总聊",
      kind: "general",
      role: "member",
      last_body: "欢迎分享校园里的新鲜事。",
      unread: 2,
    },
    {
      id: 12,
      name: "计算机工程学院",
      kind: "college",
      role: "member",
      last_body: "课程教材信息可以在这里交流。",
      unread: 0,
    },
  ];
  const supportRoom = {
    id: 10,
    name: "在线客服 · 演示会话",
    kind: "support",
    role: "member",
    user_id: 7,
    last_body: "你好，关于交付时间的问题可以在这里留言。",
    unread: 0,
  };
  const messages = [
    {
      id: 501,
      room_id: 9,
      user_id: 100,
      nickname: "小林同学",
      body: "教材还在，版次和照片一致。",
      created: now - 1800,
    },
    {
      id: 502,
      room_id: 9,
      user_id: 7,
      nickname: me.nickname,
      body: "好的，明天下午在图书馆门口核对实物。",
      created: now - 1200,
    },
    {
      id: 503,
      room_id: 9,
      user_id: 100,
      nickname: "小林同学",
      body: "没问题，到时见。",
      created: now - 900,
    },
    {
      id: 504,
      room_id: 11,
      user_id: 101,
      nickname: "阿晴",
      body: "欢迎分享校园里的新鲜事。",
      created: now - 1200,
    },
    {
      id: 505,
      room_id: 12,
      user_id: 102,
      nickname: "柚子",
      body: "这学期的教材信息可以在这里交流。",
      created: now - 900,
    },
    {
      id: 506,
      room_id: 10,
      user_id: 110,
      nickname: "演示客服",
      body: "你好，关于交付时间的问题可以在这里留言。本预览不会发送真实消息。",
      created: now - 600,
    },
  ];
  const orders = [
    {
      id: 601,
      buyer_id: 7,
      seller_id: 100,
      buyer: me.nickname,
      seller: "小林同学",
      status: "awaiting_payment",
      items: [data[0]],
      total: 1800,
      delivery_fee: 0,
      delivery: "pickup",
      address: "图书馆门口",
      appointment: now + 86400,
      created: now - 3600,
      ledger: [],
      notes: [],
      changes: [],
    },
    {
      id: 602,
      buyer_id: 102,
      seller_id: 7,
      buyer: "柚子",
      seller: me.nickname,
      status: "awaiting_receipt",
      items: [data[8]],
      total: 1800,
      delivery_fee: 0,
      delivery: "pickup",
      address: "学生中心门口",
      appointment: now - 3600,
      handover_at: now - 1800,
      schedule_confirmed: 1,
      created: now - 86400,
      ledger: [{ id: 1, kind: "模拟付款", amount: 1800, created: now - 7200 }],
      notes: [{ id: 1, body: "演示记录：双方已核对实物。" }],
      changes: [],
    },
    {
      id: 603,
      buyer_id: 7,
      seller_id: 101,
      buyer: me.nickname,
      seller: "阿晴",
      status: "completed",
      items: [data[1]],
      total: 1500,
      delivery_fee: 0,
      delivery: "pickup",
      address: "教学楼 A 栋",
      appointment: now - 172800,
      created: now - 259200,
      ledger: [
        { id: 2, kind: "模拟付款", amount: 1500, created: now - 172800 },
        { id: 3, kind: "模拟结算", amount: 1500, created: now - 86400 },
      ],
      notes: [],
      changes: [],
    },
  ];
  const tickets = [
    {
      id: 701,
      user_id: 7,
      nickname: me.nickname,
      type: "reschedule",
      subject: "想调整一次交付时间",
      body: "【演示工单】原约定时间临时有课，希望调整为明天下午。",
      status: "processing",
      order_id: 601,
      product_id: 1,
      created: now - 3600,
      messages: [
        {
          id: 1,
          nickname: "演示客服",
          body: "已收到说明，请和交易对方共同确认新的时间。",
          internal: false,
          created: now - 1800,
        },
      ],
    },
    {
      id: 702,
      user_id: 7,
      nickname: me.nickname,
      type: "other",
      subject: "免费送是否还需要交付费用",
      body: "【演示工单】想了解物品免费与送货费用的区别。",
      status: "resolved",
      created: now - 86400,
      reason: "已解释：物品免费不代表送货费免费，以商品详情为准。",
      messages: [],
    },
  ];
  /** 合成列表遵守旧接口的筛选和分页约定，不将未知资源伪装成空成功。 */
  function readPreview(path, q) {
    if (path === "/posts") {
      let result = posts.filter(
        (p) =>
          (!q.get("id") || p.id === Number(q.get("id"))) &&
          (!q.get("q") || p.body.includes(q.get("q"))) &&
          (!q.get("author") || p.user_id === Number(q.get("author"))) &&
          (!q.get("topic") || p.topic === q.get("topic")) &&
          (!q.get("forum") || ["交换人生", "代拿快递"].includes(p.topic)),
      );
      return result.slice(
        Number(q.get("offset") || 0),
        Number(q.get("offset") || 0) + Number(q.get("limit") || 20),
      );
    }
    if (path === "/comments")
      return comments.filter(
        (c) =>
          c.post_id === Number(q.get("id")) &&
          c.id > Number(q.get("after") || 0),
      );
    if (path === "/wants")
      return wants
        .filter((w) => !q.get("q") || w.keyword.includes(q.get("q")))
        .slice(
          Number(q.get("offset") || 0),
          Number(q.get("offset") || 0) + Number(q.get("limit") || 20),
        );
    if (path === "/want")
      return wants.find((w) => w.id === Number(q.get("id")));
    if (path === "/rooms") return { joined: rooms, my_support: supportRoom };
    if (path === "/messages")
      return messages.filter((m) => m.room_id === Number(q.get("room_id")));
    if (path === "/messages/receipts")
      return {
        total: 2,
        readers: [{ user_id: 100, nickname: "小林同学", last_read_id: 503 }],
      };
    if (path === "/room/members")
      return {
        members: [
          { user_id: 7, nickname: me.nickname, role: "member" },
          { user_id: 100, nickname: "小林同学", role: "member" },
        ],
      };
    if (path === "/notifications")
      return {
        unread: 1,
        items: [
          {
            id: 801,
            body: "【演示通知】你的教材订单等待确认交付时间。",
            order_id: 601,
            created: now - 900,
            read_at: 0,
          },
        ],
      };
    if (path === "/orders") return orders;
    if (path === "/order")
      return orders.find((o) => o.id === Number(q.get("id")));
    if (path === "/offers")
      return [
        {
          id: 901,
          product_id: 4,
          seller_id: 103,
          buyer_id: 7,
          title: data[3].title,
          amount: 2300,
          status: "pending",
          created: now - 1800,
        },
      ];
    if (path === "/tickets") return tickets;
    if (path === "/ticket")
      return tickets.find((t) => t.id === Number(q.get("id")));
    if (path === "/credit/history") return [];
    if (path === "/friends")
      return {
        friends: [
          {
            id: 1,
            user_id: 100,
            nickname: "小林同学",
            college: "计算机工程学院",
            message: "教材交流",
          },
        ],
        incoming: [
          {
            id: 2,
            user_id: 101,
            nickname: "阿晴",
            college: "计算机工程学院",
            message: "想交流教材",
          },
        ],
        outgoing: [],
      };
    if (path === "/friend/state") return { state: "accepted" };
    if (path === "/user/profile") return me;
    if (path === "/profile") {
      const id = Number(q.get("id"));
      return {
        user: {
          ...me,
          id,
          nickname:
            data.find((p) => p.seller_id === id)?.nickname || "演示同学",
          bio: "这是一份合成卖家资料。",
        },
        products: data.filter((p) => p.seller_id === id),
      };
    }
    if (path === "/my-products") return data.filter((p) => p.seller_id === 7);
    if (path === "/product") {
      const product = data.find((p) => p.id === Number(q.get("id")));
      return product
        ? { ...product, favorited: favorites.has(product.id) }
        : undefined;
    }
  }
  globalThis.fetch = async (input, options = {}) => {
    const url = new URL(String(input), "http://preview.invalid");
    if (
      (options.method || "GET").toUpperCase() !== "GET" &&
      url.pathname !== "/api/react"
    )
      return Response.json(
        { error: "预览仅展示页面；此提交未执行，请在连接测试后端后操作。" },
        { status: 403 },
      );
    const record = readPreview(
      url.pathname.replace(/^\/api/, ""),
      url.searchParams,
    );
    if (record !== undefined) return Response.json(record);
    if (url.pathname === "/api/config")
      return Response.json({
        auth_mode: "password",
        colleges: [{ name: "计算机工程学院", source_name: "计算机工程学院" }],
        grades: ["大一", "大二", "大三", "大四"],
        buildings: ["图书馆门口", "教学楼 A 栋"],
      });
    if (url.pathname === "/api/me") return Response.json(me);
    if (url.pathname === "/api/badges")
      return Response.json({ notifications: 0, chat: 0 });
    if (url.pathname === "/api/products") {
      const q = url.searchParams;
      let rows = data.filter(
        (p) =>
          (!q.get("q") || p.title.includes(q.get("q"))) &&
          (!q.get("category") || p.category === q.get("category")) &&
          (!q.get("favorite") || favorites.has(p.id)),
      );
      if (q.get("sort") === "price")
        rows = [...rows].sort((a, b) => a.price - b.price);
      if (q.has("limit")) {
        const size = Number(q.get("limit")),
          page = Number(q.get("page") || 1);
        rows = rows.slice((page - 1) * size, page * size);
      }
      return Response.json(
        rows.map((p) => ({ ...p, favorited: favorites.has(p.id) })),
      );
    }
    if (url.pathname === "/api/react" && options.method === "POST") {
      const body = JSON.parse(String(options.body));
      if (
        !data.some((p) => p.id === body.product_id) ||
        body.kind !== "favorite" ||
        typeof body.on !== "boolean"
      )
        return Response.json({ error: "合成收藏参数不正确" }, { status: 400 });
      if (body.on) favorites.add(body.product_id);
      else favorites.delete(body.product_id);
      return Response.json({ ok: true });
    }
    return Response.json(
      { error: "预览中没有这条演示记录；不会转发到真实业务服务。" },
      { status: 404 },
    );
  };
}
