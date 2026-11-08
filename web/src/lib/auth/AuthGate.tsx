// ログインの門番。hosted（CloudFront で配る版）のときだけ、ログインするまで中身を見せない。
// dev（npm run dev）はログインなしで中身を見せる。
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { DATA_MODE } from "../dataSource";
import LoginScreen from "../../components/LoginScreen";
import { completeSignInIfReturning, currentUser, signIn, signOut, type SignedInUser } from "./authClient";

interface AuthState {
  /** ログイン中のユーザー。ログインのない版（dev）では null */
  user: SignedInUser | null;
  signOut: () => Promise<void>;
}

const NO_AUTH: AuthState = { user: null, signOut: async () => {} };

const AuthContext = createContext<AuthState>(NO_AUTH);

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

export default function AuthGate({ children }: { children: ReactNode }) {
  if (DATA_MODE !== "hosted") {
    return <AuthContext.Provider value={NO_AUTH}>{children}</AuthContext.Provider>;
  }
  return <HostedAuthGate>{children}</HostedAuthGate>;
}

type GateState = { status: "checking" } | { status: "signedOut"; error?: string } | { status: "signedIn"; user: SignedInUser };

function HostedAuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>({ status: "checking" });

  useEffect(() => {
    checkSignIn().then(setState);
  }, []);

  if (state.status === "checking") return null;
  if (state.status === "signedOut") return <LoginScreen error={state.error} onSignIn={signIn} />;
  return <AuthContext.Provider value={{ user: state.user, signOut }}>{children}</AuthContext.Provider>;
}

async function checkSignIn(): Promise<GateState> {
  try {
    await completeSignInIfReturning();
    const user = await currentUser();
    return user ? { status: "signedIn", user } : { status: "signedOut" };
  } catch (e) {
    return { status: "signedOut", error: `ログインに失敗しました：${(e as Error).message}` };
  }
}
