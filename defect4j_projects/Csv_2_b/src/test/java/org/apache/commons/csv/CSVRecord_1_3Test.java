package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class CSVRecord_1_3Test {

    @Test
    @Timeout(8000)
    public void testConstructor_withValuesAndMappingAndCommentAndRecordNumber() throws Exception {
        String[] values = new String[]{"value1", "value2"};
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        String comment = "This is a comment";
        long recordNumber = 123L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        // Validate private fields by reflection
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);
        String[] actualValues = (String[]) valuesField.get(record);
        assertArrayEquals(values, actualValues);

        Field mappingField = CSVRecord.class.getDeclaredField("mapping");
        mappingField.setAccessible(true);
        @SuppressWarnings("unchecked")
        Map<String, Integer> actualMapping = (Map<String, Integer>) mappingField.get(record);
        assertEquals(mapping, actualMapping);

        Field commentField = CSVRecord.class.getDeclaredField("comment");
        commentField.setAccessible(true);
        String actualComment = (String) commentField.get(record);
        assertEquals(comment, actualComment);

        Field recordNumberField = CSVRecord.class.getDeclaredField("recordNumber");
        recordNumberField.setAccessible(true);
        long actualRecordNumber = recordNumberField.getLong(record);
        assertEquals(recordNumber, actualRecordNumber);
    }

    @Test
    @Timeout(8000)
    public void testConstructor_withNullValues_setsEmptyStringArray() throws Exception {
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 0L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance((Object) null, mapping, comment, recordNumber);

        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);
        String[] actualValues = (String[]) valuesField.get(record);
        assertNotNull(actualValues);
        assertEquals(0, actualValues.length);
    }
}