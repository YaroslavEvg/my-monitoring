#!/bin/bash
#shellcheck disable=2016
echo '

#!/bin/bash
../../update_version_script.sh

major_version=2
minor_version=0
path_version=0
# Путь к файлу с номером версии
version_file="version.txt"

# Читаем текущий номер версии из файла
version=$(cat $version_file)

# Используем регулярное выражение для извлечения числа в версии
if [[ $version =~ v\.[0-9]+\.[0-9]+\.[0-9]+\.([0-9]+) ]]; then
    current_version="${BASH_REMATCH[1]}"
else
    current_version=0
fi

# Увеличиваем номер версии на 1
new_version=$((current_version + 1))

# Формат даты: ДД.ММ.ГГГГ
#date_format=" %H:%M:%S""
# Получаем текущую дату в указанном формате
current_date=$(date +"%d.%m.%Y")

# Сохраняем новый номер версии и дату в файл
echo "v.$major_version.$minor_version.$path_version.$new_version $current_date" > $version_file

# Добавляем изменения в текущий коммит
git add $version_file

# Выводим сообщение о новом номере версии
echo "New version: v.$major_version.$minor_version.$path_version.$new_version $current_date"

cloc $(git ls-files)
cloc $(git ls-files) | tail -n +2 > summary_code.txt
git add summary_code.txt

' >.git/hooks/pre-commit

chmod +x .git/hooks/pre-commit
