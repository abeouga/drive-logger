// amazon-cognito-identity-js が中で使う buffer（4.x）は、Node の `global` があるものとして書かれている。
// ブラウザには無いので、ライブラリより先にこのモジュールを読み込み、globalThis を `global` として見せる。
const scope = globalThis as { global?: unknown };
scope.global ??= globalThis;

export {};
