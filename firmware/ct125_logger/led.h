// LED のタスク：動作の状態（記録中・GPS・送信中・待機・NG）を点滅の仕方で示す（README の「LED の見方」）
#pragma once
#include <Arduino.h>

void ledTask(void *);
