#pragma once
// PC でテストするための Arduino の String の代わり（json_lite.h が使うところだけ）。
#include <cstdlib>
#include <string>

class String {
 public:
  String() = default;
  String(const char *text) : s_(text) {}
  String(const std::string &text) : s_(text) {}
  int length() const { return static_cast<int>(s_.size()); }
  char operator[](int i) const { return s_[static_cast<size_t>(i)]; }
  int indexOf(const String &what, int from = 0) const {
    size_t at = s_.find(what.s_, static_cast<size_t>(from < 0 ? 0 : from));
    return at == std::string::npos ? -1 : static_cast<int>(at);
  }
  String substring(int from) const { return String(s_.substr(static_cast<size_t>(from))); }
  bool startsWith(const char *prefix) const { return s_.rfind(prefix, 0) == 0; }
  long toInt() const { return std::strtol(s_.c_str(), nullptr, 10); }
  String &operator+=(char c) { s_ += c; return *this; }
  friend String operator+(const String &a, const char *b) { return String(a.s_ + b); }
  bool operator==(const char *other) const { return s_ == other; }
  const char *c_str() const { return s_.c_str(); }

 private:
  std::string s_;
};
