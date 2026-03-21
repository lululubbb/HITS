package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CSVRecord_1_6Test {

    @Test
    @Timeout(8000)
    void testCSVRecordConstructorWithValuesAndMapping() throws Exception {
        String[] values = new String[] {"a", "b", "c"};
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        String comment = "comment";
        long recordNumber = 123L;

        // Use reflection to get the constructor and make it accessible
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);

        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        // Validate fields via reflection
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);
        assertArrayEquals(values, (String[]) valuesField.get(record));

        Field mappingField = CSVRecord.class.getDeclaredField("mapping");
        mappingField.setAccessible(true);
        assertEquals(mapping, mappingField.get(record));

        Field commentField = CSVRecord.class.getDeclaredField("comment");
        commentField.setAccessible(true);
        assertEquals(comment, commentField.get(record));

        Field recordNumberField = CSVRecord.class.getDeclaredField("recordNumber");
        recordNumberField.setAccessible(true);
        assertEquals(recordNumber, recordNumberField.getLong(record));
    }

    @Test
    @Timeout(8000)
    void testCSVRecordConstructorWithNullValues() throws Exception {
        String[] values = null;
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 0L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);

        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);
        String[] actualValues = (String[]) valuesField.get(record);
        assertNotNull(actualValues);
        assertEquals(0, actualValues.length);

        Field mappingField = CSVRecord.class.getDeclaredField("mapping");
        mappingField.setAccessible(true);
        assertEquals(mapping, mappingField.get(record));

        Field commentField = CSVRecord.class.getDeclaredField("comment");
        commentField.setAccessible(true);
        assertNull(commentField.get(record));

        Field recordNumberField = CSVRecord.class.getDeclaredField("recordNumber");
        recordNumberField.setAccessible(true);
        assertEquals(recordNumber, recordNumberField.getLong(record));
    }
}