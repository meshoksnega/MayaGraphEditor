"""UI translations (Phase 3).

Blender translates labels, operator names and property names on its own once
they are registered here; switch language in Preferences > Interface >
Translation.  To add a language, add a column to TABLE (Blender locale code)
and fill in the strings; missing entries simply stay in English.
"""

import bpy

LOCALES = ("ru_RU", "es")

# English -> (Russian, Spanish)
TABLE = {
    # tools / panels
    "Key Stats": ("Параметры ключей", "Datos de claves"),
    "Tangents": ("Касательные", "Tangentes"),
    "Buffer Curve": ("Буферная кривая", "Curva búfer"),
    "Simplify": ("Упрощение", "Simplificar"),
    "Retime / Region": ("Ретайм / Область", "Retiming / Región"),
    "Tween": ("Промежуточный ключ", "Intermedio"),
    "Curves": ("Кривые", "Curvas"),
    "Smooth": ("Сглаживание", "Suavizado"),
    "Mocap Cleanup": ("Очистка мокапа", "Limpieza de mocap"),
    "Time Warp": ("Деформация времени", "Deformación de tiempo"),
    "Enabled Tools": ("Включённые инструменты", "Herramientas activas"),
    "Updates": ("Обновления", "Actualizaciones"),
    "One-Click Tangents": ("Касательные в один клик", "Tangentes en un clic"),
    "Buffer / Ghost Curve": ("Буферная / призрачная кривая", "Curva búfer / fantasma"),
    "Curve Simplify (live preview)": ("Упрощение кривой (живой просмотр)",
                                      "Simplificar curva (vista en vivo)"),
    "Retiming Lattice": ("Решётка ретайма", "Rejilla de retiming"),
    "Curves (Infinity, Euler Filter)": ("Кривые (бесконечность, фильтр Эйлера)",
                                        "Curvas (infinito, filtro Euler)"),
    "Key Stats (frame / value fields)": ("Параметры ключей (кадр / значение)",
                                         "Datos de claves (fotograma / valor)"),
    "Tween / Breakdown slider": ("Ползунок промежуточного ключа", "Deslizador de intermedios"),
    "Smooth (live preview)": ("Сглаживание (живой просмотр)", "Suavizado (vista en vivo)"),
    "Time Warp (ease timing)": ("Деформация времени (замедления)",
                                "Deformación de tiempo (aceleraciones)"),
    "Mocap Cleanup (bake, simplify, tangents)": ("Очистка мокапа (запекание, упрощение, касательные)",
                                                 "Limpieza de mocap (hornear, simplificar, tangentes)"),
    # tangent types
    "Spline": ("Сплайн", "Spline"),
    "Linear": ("Линейная", "Lineal"),
    "Flat": ("Плоская", "Plana"),
    "Stepped": ("Ступенчатая", "Escalonada"),
    "Plateau": ("Плато", "Meseta"),
    "Clamped": ("Ограниченная", "Limitada"),
    "Both": ("Обе", "Ambas"),
    "In": ("Вход", "Entrada"),
    "Out": ("Выход", "Salida"),
    "Break": ("Разбить", "Romper"),
    "Unify": ("Объединить", "Unificar"),
    "New Keys": ("Новые ключи", "Claves nuevas"),
    "Custom": ("Своя", "Personalizada"),
    "Side": ("Сторона", "Lado"),
    "Set Tangent": ("Задать касательную", "Fijar tangente"),
    # ghost
    "Snapshot": ("Снимок", "Captura"),
    "Swap": ("Поменять", "Intercambiar"),
    "Clear": ("Очистить", "Borrar"),
    "Clear All": ("Очистить все", "Borrar todo"),
    "Show Ghosts": ("Показывать призраки", "Mostrar fantasmas"),
    "Slot": ("Слот", "Ranura"),
    "Line Width": ("Толщина линии", "Grosor de línea"),
    "Style": ("Стиль", "Estilo"),
    "Solid": ("Сплошная", "Sólida"),
    "Dashed": ("Пунктир", "Discontinua"),
    "Ghost Range": ("Диапазон призрака", "Rango del fantasma"),
    "Range": ("Диапазон", "Rango"),
    "Key Range": ("Диапазон ключей", "Rango de claves"),
    "Scene Range": ("Диапазон сцены", "Rango de la escena"),
    "Save Ghosts in File": ("Сохранять призраки в файле", "Guardar fantasmas en el archivo"),
    "Color A": ("Цвет A", "Color A"),
    "Color B": ("Цвет B", "Color B"),
    "Color C": ("Цвет C", "Color C"),
    # simplify / sliders
    "Simplify Selected Keys": ("Упростить выбранные ключи", "Simplificar claves seleccionadas"),
    "Tolerance": ("Допуск", "Tolerancia"),
    "Apply": ("Применить", "Aplicar"),
    "Cancel": ("Отмена", "Cancelar"),
    "Select 3+ consecutive keys.": ("Выберите 3+ ключа подряд.", "Selecciona 3+ claves seguidas."),
    "Ends of each run are kept.": ("Крайние ключи сохраняются.", "Se conservan los extremos."),
    "Tween Selected Keys": ("Промежуточное значение для ключей", "Intermedio de claves seleccionadas"),
    "Key at Playhead": ("Ключ на текущем кадре", "Clave en el cabezal"),
    "Smooth Selected Keys": ("Сгладить выбранные ключи", "Suavizar claves seleccionadas"),
    "Blur": ("Размытие", "Desenfoque"),
    "Amount": ("Сила", "Cantidad"),
    "Shape": ("Форма", "Forma"),
    "Ease In": ("Замедление в начале", "Entrada suave"),
    "Ease Out": ("Замедление в конце", "Salida suave"),
    "In/Out": ("Вход/выход", "Entrada/salida"),
    # retime / region
    "Retime Selection": ("Ретайм выделения", "Retiming de la selección"),
    "Scope": ("Охват", "Alcance"),
    "Selected Keys": ("Выбранные ключи", "Claves seleccionadas"),
    "Whole Rig": ("Весь риг", "Rig completo"),
    "Ripple Later Keys": ("Сдвигать последующие ключи", "Desplazar claves posteriores"),
    "Snap To Whole Frames": ("Привязка к целым кадрам", "Ajustar a fotogramas enteros"),
    "Value Handles": ("Ручки значений", "Asas de valor"),
    "Time": ("Время", "Tiempo"),
    "Values": ("Значения", "Valores"),
    "Anchor": ("Опора", "Anclaje"),
    "Start": ("Начало", "Inicio"),
    "Center": ("Центр", "Centro"),
    "End": ("Конец", "Final"),
    "Playhead": ("Текущий кадр", "Cabezal"),
    "Length": ("Длина", "Duración"),
    "Fit Preview Range": ("По диапазону предпросмотра", "Ajustar al rango de vista previa"),
    "Fit Markers": ("По маркерам", "Ajustar a marcadores"),
    "Pivot": ("Опорная точка", "Pivote"),
    "Zero": ("Ноль", "Cero"),
    "First Key": ("Первый ключ", "Primera clave"),
    "Last Key": ("Последний ключ", "Última clave"),
    "Scale": ("Масштаб", "Escala"),
    "Scale Time": ("Масштаб времени", "Escalar tiempo"),
    "Scale Values": ("Масштаб значений", "Escalar valores"),
    "Value Scale": ("Масштаб значений", "Escala de valores"),
    "Set Length": ("Задать длину", "Fijar duración"),
    # curves / stats / cleanup
    "Show Extrapolation": ("Показывать экстраполяцию", "Mostrar extrapolación"),
    "Euler Filter": ("Фильтр Эйлера", "Filtro Euler"),
    "Set Infinity": ("Задать бесконечность", "Fijar infinito"),
    "Absolute": ("Абсолютно", "Absoluto"),
    "Relative": ("Относительно", "Relativo"),
    "Frame": ("Кадр", "Fotograma"),
    "Value": ("Значение", "Valor"),
    "No keyframes selected": ("Ключи не выбраны", "No hay claves seleccionadas"),
    "Rotation shown in degrees": ("Вращение в градусах", "Rotación en grados"),
    "Values differ: average shown": ("Значения разные: показано среднее",
                                     "Valores distintos: se muestra la media"),
    "Clean Up Selected Keys": ("Очистить выбранные ключи", "Limpiar claves seleccionadas"),
    "Bake to Every Frame": ("Запечь на каждый кадр", "Hornear en cada fotograma"),
    "Keep": ("Оставить", "Mantener"),
    # preferences / updater
    "Check for Updates": ("Проверить обновления", "Buscar actualizaciones"),
    "Check for updates on startup": ("Проверять обновления при запуске",
                                     "Buscar actualizaciones al iniciar"),
    "Install Update": ("Установить обновление", "Instalar actualización"),
    "Release Notes": ("Что нового", "Notas de la versión"),
    "All Releases": ("Все версии", "Todas las versiones"),
    "Shortcuts (Graph Editor)": ("Горячие клавиши (редактор графов)",
                                 "Atajos (editor de gráficas)"),
    "Tools (each can be switched off independently):": (
        "Инструменты (каждый можно отключить отдельно):",
        "Herramientas (cada una se puede desactivar por separado):"),
    "Find the tools in the Graph Editor sidebar (N) > Maya tab.": (
        "Инструменты: боковая панель редактора графов (N) > вкладка Maya.",
        "Herramientas: barra lateral del editor de gráficas (N) > pestaña Maya."),
    "Tangent buttons in the Graph Editor header": ("Кнопки касательных в заголовке редактора графов",
                                                   "Botones de tangentes en la cabecera del editor"),
    "Use theme colours for on-screen bars and the lattice": (
        "Цвета темы для экранных панелей и решётки",
        "Colores del tema para barras y rejilla en pantalla"),
}

_CONTEXTS = ("*", "Operator")


def build():
    out = {loc: {} for loc in LOCALES}
    for en, row in TABLE.items():
        for loc, text in zip(LOCALES, row):
            if text:
                for ctx in _CONTEXTS:
                    out[loc][(ctx, en)] = text
    return out


def register():
    try:
        bpy.app.translations.register(__package__, build())
    except ValueError:  # already registered (reload)
        bpy.app.translations.unregister(__package__)
        bpy.app.translations.register(__package__, build())


def unregister():
    try:
        bpy.app.translations.unregister(__package__)
    except Exception:
        pass


def iface(text):
    """Translate a label built at runtime (formatted strings)."""
    return bpy.app.translations.pgettext_iface(text)
