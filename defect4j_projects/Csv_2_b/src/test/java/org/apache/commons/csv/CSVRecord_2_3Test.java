package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_2_3Test {

    private CSVRecord csvRecord;
    private String[] values;
    private Map<String, Integer> mapping;

    @BeforeEach
    void setUp() {
        values = new String[] { "value0", "value1", "value2" };
        mapping = new HashMap<>();
        mapping.put("col0", 0);
        mapping.put("col1", 1);
        mapping.put("col2", 2);
        csvRecord = new CSVRecord(values, mapping, "comment", 42L);
    }

    @Test
    @Timeout(8000)
    void testGetByIndex_ValidIndices() {
        assertEquals("value0", csvRecord.get(0));
        assertEquals("value1", csvRecord.get(1));
        assertEquals("value2", csvRecord.get(2));
    }

    @Test
    @Timeout(8000)
    void testGetByIndex_NegativeIndex_ThrowsArrayIndexOutOfBoundsException() {
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(-1));
    }

    @Test
    @Timeout(8000)
    void testGetByIndex_IndexEqualToLength_ThrowsArrayIndexOutOfBoundsException() {
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(values.length));
    }

    @Test
    @Timeout(8000)
    void testGetByIndex_IndexGreaterThanLength_ThrowsArrayIndexOutOfBoundsException() {
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> csvRecord.get(values.length + 1));
    }

    @Test
    @Timeout(8000)
    void testGetByIndex_EmptyValuesArray_ThrowsArrayIndexOutOfBoundsException() {
        CSVRecord emptyValuesRecord = new CSVRecord(new String[0], Collections.emptyMap(), null, 0L);
        assertThrows(ArrayIndexOutOfBoundsException.class, () -> emptyValuesRecord.get(0));
    }

    @Test
    @Timeout(8000)
    void testPrivateMethodInvocationUsingReflection() throws Exception {
        Method valuesMethod = CSVRecord.class.getDeclaredMethod("values");
        valuesMethod.setAccessible(true);
        String[] returnedValues = (String[]) valuesMethod.invoke(csvRecord);
        assertArrayEquals(values, returnedValues);
    }
}