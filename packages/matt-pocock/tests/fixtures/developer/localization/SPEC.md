# localization

fileCount(locale,count) formats validated nonnegative integer counts. English en/en-US and unknown locale fallback: exactly '1 file' for one and '<count> files' otherwise. Chinese zh/zh-CN: '<count> 个文件' including zero and one. Preserve Unicode and zero; no network, dependency, translation API or unrelated locale support.
Given English one, then use singular. Given English zero, then plural. Given Chinese, then use the same Chinese noun for every count. Given unsupported locale, then fall back to English.
