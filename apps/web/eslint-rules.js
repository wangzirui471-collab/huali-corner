/** 项目自己的窄规则：检查手写具名方法具有中文说明，便于后续阅读。 */
export const methodComments = {
  meta: {
    type: 'suggestion',
    schema: [],
    messages: { missing: '请为此函数或方法添加中文 JSDoc，说明用途及必要的输入、结果。' },
  },
  /** 取得源码注释并检查具名函数和类方法；匿名回调由所在步骤说明用途。 */
  create(context) {
    /** export 的注释通常附在外层声明上，因此同时检查当前节点和声明父节点。 */
    function check(node) {
      const source = context.sourceCode;
      const candidates = [node];
      if (node.parent?.type === 'ExportNamedDeclaration') candidates.push(node.parent);
      const documented = candidates.some((candidate) =>
        source
          .getCommentsBefore(candidate)
          .some(
            (comment) =>
              comment.type === 'Block' &&
              comment.value.startsWith('*') &&
              /\p{Script=Han}/u.test(comment.value),
          ),
      );
      if (!documented) context.report({ node, messageId: 'missing' });
    }
    return { FunctionDeclaration: check, MethodDefinition: check };
  },
};
