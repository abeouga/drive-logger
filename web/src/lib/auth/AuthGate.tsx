// ログインの門番。ログインするまで中身を見せない（公開版も dev も同じ。dev はデータ API を公開ドメインに中継する）。
// ログインしたら /api/me でグループを読み、admin なら書き換えのボタン（消す・戻す・切り替え）を出す。最終的な判断は API がする。
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import LoginScreen from "../../components/LoginScreen";
import { LOCAL_API, apiJson } from "../dataSource";
import type { Me } from "../types";
import { currentUser, signIn, signOut, type Credentials, type SignedInUser } from "./authClient";

const ADMIN_GROUP = "admin"; // contracts/common.json の admin_group

interface AuthState {
  user: SignedInUser | null;
  isAdmin: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({ user: null, isAdmin: false, signOut: async () => {} });

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

type GateState = { status: "checking" } | { status: "signedOut"; error?: string } | { status: "signedIn"; user: SignedInUser; isAdmin: boolean };

export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>({ status: "checking" });

  useEffect(() => {
    checkSignIn().then(setState);
  }, []);

  /** 入力欄の値でログインし、続けて権限を読む。失敗したら投げる（ログイン画面が理由を出す）。 */
  async function submit(credentials: Credentials): Promise<void> {
    await signIn(credentials);
    const next = await checkSignIn();
    if (next.status === "signedOut") throw new Error(next.error ?? "ログインできませんでした");
    setState(next);
  }

  /** ログアウトして、ログイン画面に戻す（Cognito の画面へは移らない）。 */
  async function leave(): Promise<void> {
    await signOut();
    setState({ status: "signedOut" });
  }

  if (state.status === "checking") return null;
  if (state.status === "signedOut") return <LoginScreen notice={state.error} onSignIn={submit} />;
  return <AuthContext.Provider value={{ user: state.user, isAdmin: state.isAdmin, signOut: leave }}>{children}</AuthContext.Provider>;
}

async function checkSignIn(): Promise<GateState> {
  try {
    if (LOCAL_API) {
      // npm run dev:local：ログインしない。手元のデータ API が「手元の開発者」として扱う
      const me = await apiJson<Me>("me");
      return { status: "signedIn", user: { username: me.username }, isAdmin: me.groups.includes(ADMIN_GROUP) };
    }
    const user = await currentUser();
    if (!user) return { status: "signedOut" };
    const me = await apiJson<Me>("me");
    return { status: "signedIn", user, isAdmin: me.groups.includes(ADMIN_GROUP) };
  } catch (e) {
    return { status: "signedOut", error: `ログインに失敗しました：${(e as Error).message}` };
  }
}
