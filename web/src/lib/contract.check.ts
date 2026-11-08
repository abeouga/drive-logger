// 画面用 JSON・データ API の応答の約束（contracts/app/・contracts/api/）と types.ts の型の突き合わせ。`npm run typecheck`（tsc -b）で確かめる。
// 見本（contracts/examples/app/）は pipeline のテストが本物の書き出しの関数から作ったもの。
// 画面のコードからは読み込まないので、ビルドには入らない（型を確かめるためだけのファイル）。
import rides from "../../../contracts/examples/app/rides.json";
import ride from "../../../contracts/examples/app/ride.json";
import spec from "../../../contracts/examples/app/spec.json";
import wave from "../../../contracts/examples/app/wave.json";
import apiRides from "../../../contracts/examples/api/rides.json";
import apiRuns from "../../../contracts/examples/api/runs.json";
import apiModels from "../../../contracts/examples/api/models.json";
import modelRecord from "../../../contracts/examples/records/model.json";
import type { LedgerRide, ModelItem, ModelRecord, ModelsResponse, RideColumns, RideData, RidesFile, RidesResponse, RideSummary, RunInfo, RunsResponse, SpecMeta, WaveFile, Waveform } from "./types";

// JSON から読んだ型は、文字列の候補（"full" | "partial" | "none" など）が string に広がるので、比べる側も広げる
type Widen<T> = T extends string
  ? string
  : T extends number
    ? number
    : T extends boolean
      ? boolean
      : T extends null
        ? null
        : T extends readonly (infer U)[]
          ? Widen<U>[]
          : T extends object
            ? { [K in keyof T]: Widen<T[K]> }
            : T;

// 1. 見本が型に当てはまる（型にある項目が見本に全部あり、値の種類が合う）
export const ridesFits: Widen<RidesFile> = rides;
export const rideFits: Widen<RideData> = ride;
export const specFits: Widen<SpecMeta> = spec;
export const waveFits: Widen<WaveFile> = wave;
export const apiRidesFits: Widen<RidesResponse> = apiRides;
export const apiRunsFits: Widen<RunsResponse> = apiRuns;
export const apiModelsFits: Widen<ModelsResponse> = apiModels;
export const modelRecordFits: Widen<ModelRecord> = modelRecord;

// 2. 見本に、型に無い項目が無い（書き出しに足した項目を型に足し忘れていない）
type NoExtraKeys<Json, Type> = [Exclude<keyof Json, keyof Type>] extends [never] ? true : false;
export const summaryKeys: NoExtraKeys<(typeof rides)["rides"][number], RideSummary> = true;
export const rideKeys: NoExtraKeys<typeof ride, RideData> = true;
export const columnKeys: NoExtraKeys<(typeof ride)["columns"], RideColumns> = true;
export const specKeys: NoExtraKeys<typeof spec, SpecMeta> = true;
export const waveKeys: NoExtraKeys<(typeof wave)["windows"][number], Waveform> = true;
export const ledgerRideKeys: NoExtraKeys<(typeof apiRides)["rides"][number], LedgerRide> = true;
export const runKeys: NoExtraKeys<(typeof apiRuns)["runs"][number], RunInfo> = true;
export const modelItemKeys: NoExtraKeys<(typeof apiModels)["models"][number], ModelItem> = true;
