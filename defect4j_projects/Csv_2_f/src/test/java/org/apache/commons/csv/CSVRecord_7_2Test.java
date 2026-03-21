package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Iterator;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_7_2Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;
    private String comment;
    private long recordNumber;

    @BeforeEach
    void setUp() throws Exception {
        values = new String[] { "a", "b", "c" };
        mapping = mock(Map.class);
        comment = "testComment";
        recordNumber = 123L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        csvRecord = constructor.newInstance((Object) values, mapping, comment, recordNumber);
    }

    @Test
    @Timeout(8000)
    void testIterator_returnsIteratorOverValues() {
        Iterator<String> iterator = csvRecord.iterator();
        assertNotNull(iterator);

        // Collect all elements from iterator
        String[] iteratedValues = new String[values.length];
        int i = 0;
        while (iterator.hasNext()) {
            iteratedValues[i++] = iterator.next();
        }
        assertArrayEquals(values, iteratedValues);
    }

    @Test
    @Timeout(8000)
    void testIterator_emptyValuesArray() throws Exception {
        // Create CSVRecord with empty values array
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord emptyRecord = constructor.newInstance((Object) new String[0], mapping, comment, recordNumber);

        Iterator<String> iterator = emptyRecord.iterator();
        assertNotNull(iterator);
        assertFalse(iterator.hasNext());
    }

    @Test
    @Timeout(8000)
    void testIterator_reflectiveAccessToValuesField() throws Exception {
        // Use reflection to get private 'values' field and verify it matches the array used in iterator
        Field valuesField = CSVRecord.class.getDeclaredField("values");
        valuesField.setAccessible(true);
        String[] fieldValues = (String[]) valuesField.get(csvRecord);

        Iterator<String> iterator = csvRecord.iterator();
        String[] iteratedValues = new String[fieldValues.length];
        int i = 0;
        while (iterator.hasNext()) {
            iteratedValues[i++] = iterator.next();
        }
        assertArrayEquals(fieldValues, iteratedValues);
    }
}